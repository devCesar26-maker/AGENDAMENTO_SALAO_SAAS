"""Factories de usuários (accounts)."""

from django.contrib.auth import get_user_model
from factory import Faker, PostGenerationMethodCall, Sequence
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
    password = PostGenerationMethodCall("set_password", SENHA_PADRAO)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        user = super()._create(model_class, *args, **kwargs)
        user.plain_password = SENHA_PADRAO
        return user
