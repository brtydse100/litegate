import { KeyRound } from "lucide-react";
import BulkKeyEditor from "./BulkKeyEditor";

export default function AdminKeys() {
  return (
    <section className="w-full max-w-4xl space-y-5">
      <div>
        <p className="text-xs font-medium uppercase tracking-wider text-indigo-400">Administration</p>
        <h1 className="mt-1 flex items-center gap-2 text-xl font-semibold text-white"><KeyRound size={20} /> Key policies</h1>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-gray-500">
          Search the entire installation, select individual results or every matching key, and apply one policy change safely. This page never reveals key secrets.
        </p>
      </div>
      <BulkKeyEditor expanded />
    </section>
  );
}
