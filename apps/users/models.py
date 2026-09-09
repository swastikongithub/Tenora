import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """
    Required because this model drops `username` in favour of email as
    USERNAME_FIELD. Django's default UserManager.create_user() takes
    `username` as its first positional argument, so leaving it in place
    breaks both createsuperuser and any direct create_user() call.
    """

    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        # Django's version lowercases only the domain. Emails are treated
        # case-insensitively throughout this project, so lowercase the whole
        # address and make that the single rule -- applied on write and on
        # every lookup, so plain exact match on UNIQUE(email) is always right.
        return super().normalize_email(email).lower()

    def get_by_natural_key(self, username):
        # ModelBackend authenticates through here (login, admin). Normalizing
        # the input the same way storage was normalized is what keeps exact
        # match correct after normalize_email() lowercases on write.
        return self.get(**{self.model.USERNAME_FIELD: self.normalize_email(username)})

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Custom user model, keyed by email rather than username.
    Decided in Phase 1 because swapping AUTH_USER_MODEL later
    is a painful migration — locking this in now.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField(unique=True)
    # A distinct field from is_active on purpose (email-verification-spec.md
    # §1) — is_active means "administratively disabled," a different concept
    # that overloading here would conflate. Never set to True except via a
    # successful EmailVerificationService.verify() call or the one-time
    # grandfathering migration for pre-existing rows.
    email_verified = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email


class EmailVerificationToken(models.Model):
    """
    A real, DB-backed, single-use token — not stateless/signed — mirroring
    the pattern this codebase already uses for refresh-token blacklisting
    (Stage C3 §0.2). The raw token is never stored: token_hash is a plain
    SHA-256 digest (see EmailVerificationService), looked up directly rather
    than password-style-hashed, because the token is a high-entropy random
    value with no accompanying identifier to narrow the lookup — see
    email-verification-spec.md plan decision 1.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="verification_tokens"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    # NULL means unused. Set exactly once, atomically, by
    # EmailVerificationService.verify() — a second attempt with the same
    # token must fail the same way an expired one does.
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user"])]

    def __str__(self):
        return f"verification token for {self.user_id}"