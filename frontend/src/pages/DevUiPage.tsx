import { useState } from "react";
import { PageHeader } from "../components/layout/PageHeader";
import {
  Badge,
  Button,
  Card,
  Dialog,
  EmptyState,
  FormField,
  Input,
  Modal,
  Pagination,
  Skeleton,
  SkeletonList,
  Tabs,
  toast,
} from "../components/ui";

export function DevUiPage() {
  const [modalOpen, setModalOpen] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [activeTab, setActiveTab] = useState("a");

  return (
    <main className="page-content dev-ui-page">
      <PageHeader
        eyebrow="DESIGN SYSTEM"
        title="Biblioteca de interface"
        description="Referência visual dos componentes compartilhados do Éclat."
      />

      <div className="dev-ui-grid">
        <Card className="p-5">
          <h2 className="font-serif text-xl">Botões</h2>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button>Primário</Button>
            <Button variant="secondary">Secundário</Button>
            <Button variant="ghost">Ghost</Button>
            <Button disabled>Desabilitado</Button>
          </div>
        </Card>

        <Card className="p-5">
          <h2 className="font-serif text-xl">Badges</h2>
          <div className="mt-4 flex flex-wrap gap-2">
            <Badge>Neutro</Badge>
            <Badge tone="success">Sucesso</Badge>
            <Badge tone="warning">Atenção</Badge>
          </div>
        </Card>

        <Card className="p-5">
          <h2 className="font-serif text-xl">Formulário</h2>
          <FormField label="Nome" helperText="Texto de apoio">
            <Input placeholder="Digite aqui" />
          </FormField>
        </Card>

        <Card className="p-5">
          <h2 className="font-serif text-xl">Tabs</h2>
          <Tabs
            activeTab={activeTab}
            onChange={setActiveTab}
            tabs={[
              { id: "a", label: "Aba A", content: <p className="helper-copy">Conteúdo A</p> },
              { id: "b", label: "Aba B", content: <p className="helper-copy">Conteúdo B</p> },
            ]}
          />
        </Card>

        <Card className="p-5">
          <h2 className="font-serif text-xl">Feedback</h2>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => toast("Operação concluída", "success")}>
              Toast sucesso
            </Button>
            <Button variant="secondary" onClick={() => setModalOpen(true)}>
              Abrir modal
            </Button>
            <Button variant="secondary" onClick={() => setDialogOpen(true)}>
              Abrir dialog
            </Button>
          </div>
        </Card>

        <Card className="p-5">
          <h2 className="font-serif text-xl">Loading</h2>
          <Skeleton className="mb-3" height={12} width="70%" />
          <SkeletonList count={2} />
        </Card>

        <Card className="p-5">
          <h2 className="font-serif text-xl">Paginação</h2>
          <Pagination currentPage={page} totalPages={8} onPageChange={setPage} />
        </Card>

        <EmptyState title="Estado vazio">Use este padrão quando não houver registros.</EmptyState>
      </div>

      <Modal isOpen={modalOpen} onClose={() => setModalOpen(false)} title="Exemplo de modal">
        <p className="helper-copy">Conteúdo do modal com foco e tecla Esc.</p>
      </Modal>

      <Dialog
        isOpen={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onConfirm={() => setDialogOpen(false)}
        title="Confirmar ação"
        description="Dialog de confirmação padronizado."
        confirmText="Ok"
      />
    </main>
  );
}
