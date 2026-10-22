import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { z } from "zod";
import { useAuth } from "../lib/auth-context";
import { errorMessage } from "../lib/api";
import { Button, Input, FormField } from "../components/ui";

const loginSchema = z.object({
  email: z.string().email("Informe um e-mail válido"),
  password: z.string().min(1, "Informe a senha"),
});

type LoginForm = z.infer<typeof loginSchema>;

export function LoginPage() {
  const { login } = useAuth();
  const [erro, setErro] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>({ resolver: zodResolver(loginSchema) });

  async function onSubmit(values: LoginForm) {
    setErro(null);
    try {
      await login(values.email, values.password);
      window.location.assign("/app");
    } catch (e) {
      setErro(errorMessage(e));
    }
  }

  return (
    <div className="login-shell">
      <div className="login-card panel card-hover">
        <div className="login-brand">
          <span className="brand-mark">É</span>
          <span>
            <strong>Éclat</strong>
            <small>GESTÃO DO ESTÚDIO</small>
          </span>
        </div>
        <h1 className="login-title">Seu espaço, em harmonia.</h1>
        <p className="muted-copy">Acesse a gestão do seu salão ou barbearia.</p>

        <form onSubmit={handleSubmit(onSubmit)} className="register-form" noValidate>
          <FormField
            label="E-mail"
            error={errors.email?.message}
          >
            <Input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="seu@email.com"
              {...register("email")}
              className="w-full"
            />
          </FormField>

          <FormField
            label="Senha"
            error={errors.password?.message}
          >
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              {...register("password")}
              className="w-full"
            />
          </FormField>

          {erro && (
            <div role="alert" className="notice-card notice-error">
              {erro}
            </div>
          )}

          <Button
            type="submit"
            disabled={isSubmitting}
            className="button-wide register-submit"
          >
            {isSubmitting ? (
              <>
                <span className="spinner" aria-hidden="true" />
                Entrando…
              </>
            ) : (
              "Entrar"
            )}
          </Button>
        </form>
        <p className="register-footer">
          <a href="/esqueci-senha">Esqueci minha senha</a>
        </p>
        <p className="register-footer">
          Ainda não tem conta? <a href="/cadastro">Criar meu espaço</a>
        </p>
      </div>
    </div>
  );
}
