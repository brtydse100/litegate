import { KeyRound } from "lucide-react";
import BulkKeyEditor from "./BulkKeyEditor";

export default function AdminKeys() {
  return (
    <section className="w-full space-y-5">
      <div>
        <p className="text-xs font-medium text-indigo-600">Virtual keys</p>
        <h1 className="mt-1 flex items-center gap-2 text-2xl font-semibold tracking-tight text-slate-950">
          <KeyRound size={21} /> Key policies
        </h1>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">
          Search the entire installation, select individual results or every
          matching key, and apply one policy change safely. This page never
          reveals key secrets.
        </p>
      </div>
      <BulkKeyEditor expanded />
    </section>
  );
}
