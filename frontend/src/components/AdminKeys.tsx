import BulkKeyEditor from "./BulkKeyEditor";
import { PageHeader } from "./Page";

export default function AdminKeys({
  saveApiKeysInDb = false,
  enterpriseEnabled = false,
}: {
  saveApiKeysInDb?: boolean;
  enterpriseEnabled?: boolean;
}) {
  return (
    <section className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Manage"
        title="Key policies"
        description={
          <>
            Search the entire installation, select individual results or every
            matching key, and apply one policy change safely.{" "}
            {saveApiKeysInDb
              ? "Stored key secrets can be revealed by administrators."
              : "This page never reveals key secrets."}
          </>
        }
      />
      <BulkKeyEditor
        expanded
        saveApiKeysInDb={saveApiKeysInDb}
        enterpriseEnabled={enterpriseEnabled}
      />
    </section>
  );
}
