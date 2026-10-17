"""Factories de usuários (accounts)."""

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from factory import Faker, Sequence
from factory.django import DjangoModelFactory

User = get_user_model()

SENHA_PADRAO = "Senha#2026!"


class UserFactory(DjangoModelFactory):
    """
    Usuário comum por e-mail. Senha padrão válida (`SENHA_PADRAO`); para senha
    customizada use `plain_password="..."` (consumido antes de criar o model).
    """

    class Meta:
        model = User

    email = Sequence(lambda n: f"usuario{n}@exemplo.com.br")
    first_name = Faker("first_name", locale="pt_BR")
    last_name = Faker("last_name", locale="pt_BR")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        plain_password = kwargs.pop("plain_password", SENHA_PADRAO)
        kwargs["password"] = make_password(plain_password)
        user = super()._create(model_class, *args, **kwargs)
        user.plain_password = plain_password
        return user
