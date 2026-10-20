import { useState, type FormEvent } from "react";
import { api, errorMessage } from "../lib/api";
import { Button, Input, Select } from "../components/ui";

type Vertical = "SALAO" | "BARBEARIA";
type Registration = {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  organization_name: string;
  organization_phone: string;
  vertical: Vertical;
};

const initialValues: Registration = {
  first_name: "",
  last_name: "",
  email: "",
  password: "",
  organization_name: "",
  organization_phone: "",
  vertical: "SALAO",
};

export function RegisterPage() {
  const [values, setValues] = useState(initialValues);
  const [error, setError] = useState("");
  const [created, setCreated] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  function update<Field extends keyof Registration>(field: Field, value: Registration[Field]) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await api.post("/auth/register/", values);
      setCreated(true);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  }

  if (created) {
    return (
      <main className="login-shell">
        <section className="login-card panel" role="status">
          <div className="login-brand"><span className="brand-mark">É</span><span><strong>Éclat</strong><small>GESTÃO DO ESTÚDIO</small></span></div>
          <h1 className="login-title">Cadastro concluído.</h1>
          <p className="muted-copy">Sua conta e seu espaço foram criados. Entre com o e-mail e a senha cadastrados.</p>
          <a className="button-primary button-wide register-submit" href="/login">Ir para entrar</a>
        </section>
      </main>
    );
  }

  return (
    <main className="login-shell">
      <section className="register-card panel">
        <div className="login-brand"><span className="brand-mark">É</span><span><strong>Éclat</strong><small>GESTÃO DO ESTÚDIO</small></span></div>
        <h1 className="login-title">Crie seu espaço.</h1>
        <p className="muted-copy">Comece a organizar seu salão ou barbearia.</p>
        <form className="register-form" onSubmit={submit}>
          <div className="form-columns">
            <label className="field-label">Seu nome<Input autoComplete="given-name" required maxLength={150} value={values.first_name} onChange={(event) => update("first_name", event.target.value)} /></label>
            <label className="field-label">Sobrenome<Input autoComplete="family-name" maxLength={150} value={values.last_name} onChange={(event) => update("last_name", event.target.value)} /></label>
          </div>
          <label className="field-label">E-mail<Input type="email" autoComplete="email" required value={values.email} onChange={(event) => update("email", event.target.value)} /></label>
          <label className="field-label">Senha<Input type="password" autoComplete="new-password" minLength={8} required value={values.password} onChange={(event) => update("password", event.target.value)} /><span className="helper-copy">Use uma senha forte. O cadastro valida os critérios de segurança do sistema.</span></label>
          <label className="field-label">Nome do estabelecimento<Input autoComplete="organization" required maxLength={120} value={values.organization_name} onChange={(event) => update("organization_name", event.target.value)} /></label>
          <label className="field-label">Tipo de estabelecimento<Select value={values.vertical} onChange={(event) => update("vertical", event.target.value as Vertical)}><option value="SALAO">Salão</option><option value="BARBEARIA">Barbearia</option></Select></label>
          <label className="field-label">Telefone do estabelecimento <span>(opcional)</span><Input type="tel" autoComplete="tel" maxLength={20} value={values.organization_phone} onChange={(event) => update("organization_phone", event.target.value)} /></label>
          {error && <p className="notice-error" role="alert">{error}</p>}
          <Button type="submit" className="button-wide register-submit" disabled={submitting}>{submitting ? "Criando seu espaço…" : "Criar conta"}</Button>
        </form>
        <p className="register-footer">Já tem uma conta? <a href="/login">Entrar</a></p>
      </section>
    </main>
  );
}
