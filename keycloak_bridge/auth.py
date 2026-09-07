# keycloak_bridge/auth.py
import jwt
from jwt import PyJWKClient
from django.conf import settings
from django.contrib.auth import get_user_model
from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth.models import Group

User = get_user_model()

class KeycloakOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    """
    Custom OIDC backend that maps Keycloak claims to Django user fields and Wagtail groups.
    """

    def get_username(self, claims):
        """Ensure backend uses preferred_username to match filter_users_by_claims."""
        return claims.get("preferred_username")

    def filter_users_by_claims(self, claims):
        """Find existing users by Keycloak's preferred_username."""
        username = claims.get("preferred_username")
        if username:
            return User.objects.filter(username=username)
        return self.UserModel.objects.none()

    def create_user(self, claims):
        """Create a Django user from Keycloak claims."""
        user = super().create_user(claims)
        self.update_user_from_claims(user, claims)
        return user

    def update_user(self, user, claims):
        """Update an existing Django user from Keycloak claims."""
        self.update_user_from_claims(user, claims)
        return user

    def _extract_roles(self, claims):
            """Recursively search claims and standard Keycloak paths for roles."""
            
            found_roles = set()

            # 1. Check realm roles
            realm_access = claims.get("realm_access", {})
            if isinstance(realm_access, dict):
                for r in realm_access.get("roles", []):
                    if isinstance(r, str):
                        found_roles.add(r.lower())

            # 2. Check resource_access for ALL clients dynamically
            resource_access = claims.get("resource_access", {})
            if isinstance(resource_access, dict):
                for client_name, client_data in resource_access.items():
                    if isinstance(client_data, dict):
                        for r in client_data.get("roles", []):
                            if isinstance(r, str):
                                found_roles.add(r.lower())

            # 3. Check root-level roles or custom mappers
            for key in ["roles", "groups"]:
                val = claims.get(key, [])
                if isinstance(val, list):
                    for r in val:
                        if isinstance(r, str):
                            found_roles.add(r.lower())
            return found_roles

    def update_user_from_claims(self, user, claims):
        """Map Keycloak claims to Django user fields and Wagtail groups."""
        user.first_name = claims.get("given_name", "")
        user.last_name = claims.get("family_name", "")
        user.email = claims.get("email", "")

        all_roles = self._extract_roles(claims)

        # Valid Wagtail groups we manage via Keycloak roles
        valid_group_names = {"Administrators", "Moderators", "Editors"}

        # 1. Update Staff and Superuser Flags
        user.is_staff = bool(all_roles.intersection({r.lower() for r in valid_group_names}))
        user.is_superuser = "administrators" in all_roles
        user.save()

        # 2. Dynamically map exact Keycloak roles to Wagtail Django Groups
        matched_groups = []
        for role in all_roles:
            proper_name = role.capitalize()  # e.g., "editors" -> "Editors"
            if proper_name in valid_group_names:
                group, _ = Group.objects.get_or_create(name=proper_name)
                matched_groups.append(group)

        if matched_groups:
            user.groups.set(matched_groups)
        else:
            user.groups.clear()

    @staticmethod
    def generate_username(email):
        """Use email prefix as username fallback."""
        return email.split("@")[0] if email else ""


class KeycloakJWTAuthentication(BaseAuthentication):
    """
    DRF authentication class that validates Keycloak JWT access tokens.
    """

    def __init__(self):
        self._jwks_client = None

    @property
    def jwks_client(self):
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(
                settings.OIDC_OP_JWKS_ENDPOINT,
                cache_keys=True,
                lifespan=3600,
            )
        return self._jwks_client

    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]

        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience="account",
                issuer=f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}",
                options={
                    "verify_exp": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Token has expired")
        except jwt.InvalidTokenError as e:
            raise AuthenticationFailed(f"Invalid token: {str(e)}")

        user = self._get_or_create_user(payload)
        user.keycloak_claims = payload
        return (user, payload)

    def _get_or_create_user(self, payload):
        username = payload.get("preferred_username", payload["sub"])

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            if not settings.OIDC_CREATE_USER:
                raise AuthenticationFailed("User does not exist")
            user = User.objects.create(
                username=username,
                email=payload.get("email", ""),
                first_name=payload.get("given_name", ""),
                last_name=payload.get("family_name", ""),
            )

        # Quick role extraction for API tokens
        realm_roles = payload.get("realm_access", {}).get("roles", [])
        client_id = getattr(settings, "OIDC_RP_CLIENT_ID", "")
        client_roles = (
            payload.get("resource_access", {})
            .get(client_id, {})
            .get("roles", [])
        )
        all_roles = {r.lower() for r in (realm_roles + client_roles)}

        user.is_staff = bool(all_roles.intersection({"administrators", "moderators", "editors"}))
        user.is_superuser = "administrators" in all_roles
        user.save(update_fields=["is_staff", "is_superuser"])

        return user
