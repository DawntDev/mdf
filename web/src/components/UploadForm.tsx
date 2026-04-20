import { useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import type { ApiModel, DocumentState } from "../types";
import { formatBytes, formatCost } from "../utils";
import { FilePreview } from "./FilePreview";

interface UploadFormProps {
    doc: DocumentState | null;
    onDoc: (doc: DocumentState | null) => void;
    selectedModel: ApiModel | null;
    estimatedCost: number | null;
    onExtract: () => void;
    busy: boolean;
}

const LANGUAGES = [
    { code: "", label: "auto" },
    { code: "en", label: "en" },
    { code: "es", label: "es" },
    { code: "pt", label: "pt" },
    { code: "fr", label: "fr" },
    { code: "de", label: "de" },
];

const estimatePages = (size: number): number => {
    // Rough: ~50KB/page avg for PDFs, clamp 1..500
    const approx = Math.max(1, Math.round(size / (50 * 1024)));
    return Math.min(approx, 500);
};

export const UploadForm = ({
    doc,
    onDoc,
    selectedModel,
    estimatedCost,
    onExtract,
    busy,
}: UploadFormProps) => {
    const inputRef = useRef<HTMLInputElement>(null);
    const [hover, setHover] = useState(false);

    const openPicker = () => inputRef.current?.click();

    const handleFile = (file: File) => {
        const totalPages = estimatePages(file.size);
        onDoc({
            file,
            name: file.name,
            size: file.size,
            totalPages,
            startPage: 1,
            endPage: totalPages,
            aiGeneration: false,
            languageHint: "",
        });
    };

    const onFileChange = (e: ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) handleFile(file);
    };

    const onDrop = (e: DragEvent<HTMLDivElement>) => {
        e.preventDefault();
        setHover(false);
        const file = e.dataTransfer.files?.[0];
        if (file) handleFile(file);
    };

    const onDragOver = (e: DragEvent<HTMLDivElement>) => {
        e.preventDefault();
        setHover(true);
    };

    const onDragLeave = () => setHover(false);

    const update = (patch: Partial<DocumentState>) => {
        if (!doc) return;
        onDoc({ ...doc, ...patch });
    };

    const clampPage = (n: number, min: number, max: number) =>
        Math.max(min, Math.min(max, Math.floor(n) || min));

    const pagesToProcess = doc ? doc.endPage - doc.startPage + 1 : 0;

    return (
        <div className="glass p-6 md:p-8 flex flex-col gap-6">
            <div className="flex items-center justify-between">
                <div className="flex flex-col">
                    <span className="eyebrow">step · 01</span>
                    <h2 className="text-lg font-medium text-ink">
                        Upload a document
                    </h2>
                </div>
                {doc && (
                    <button
                        type="button"
                        onClick={() => onDoc(null)}
                        className="chip is-danger"
                    >
                        clear
                    </button>
                )}
            </div>

            {!doc ? (
                <div
                    onClick={openPicker}
                    onDrop={onDrop}
                    onDragOver={onDragOver}
                    onDragLeave={onDragLeave}
                    className={`dropzone ${
                        hover ? "is-hover" : ""
                    } rounded-2xl p-10 flex flex-col items-center justify-center text-center cursor-pointer gap-3`}
                >
                    <div className="font-mono text-2xl text-ink-dim">+</div>
                    <div className="text-sm text-ink">
                        Drop a PDF, image, or docx here
                    </div>
                    <div className="eyebrow">or click to browse</div>
                    <input
                        ref={inputRef}
                        type="file"
                        accept=".pdf,.png,.jpg,.jpeg,.webp,.tiff,.docx"
                        onChange={onFileChange}
                        className="hidden"
                    />
                </div>
            ) : (
                <div className="flex flex-col gap-5">
                    <div className="glass-soft p-4 flex items-center justify-between gap-4">
                        <div className="flex items-center gap-3 min-w-0">
                            <div className="w-10 h-10 rounded-lg bg-white/4 border border-line flex items-center justify-center font-mono text-[11px] text-ink-dim shrink-0">
                                {doc.name.split(".").pop()?.toLowerCase() ?? "doc"}
                            </div>
                            <div className="flex flex-col min-w-0">
                                <span className="text-sm text-ink truncate">
                                    {doc.name}
                                </span>
                                <span className="font-mono text-[11px] text-ink-faint">
                                    {formatBytes(doc.size)} · ~{doc.totalPages}{" "}
                                    pages
                                </span>
                            </div>
                        </div>
                    </div>

                    <FilePreview file={doc.file} />

                    <div className="grid grid-cols-2 gap-3">
                        <div className="flex flex-col gap-2">
                            <label className="eyebrow">start page</label>
                            <input
                                type="number"
                                min={1}
                                max={doc.endPage}
                                value={doc.startPage}
                                onChange={(e) =>
                                    update({
                                        startPage: clampPage(
                                            Number(e.target.value),
                                            1,
                                            doc.endPage,
                                        ),
                                    })
                                }
                                className="field px-3 py-2.5 font-mono text-sm"
                            />
                        </div>
                        <div className="flex flex-col gap-2">
                            <label className="eyebrow">end page</label>
                            <input
                                type="number"
                                min={doc.startPage}
                                max={doc.totalPages}
                                value={doc.endPage}
                                onChange={(e) =>
                                    update({
                                        endPage: clampPage(
                                            Number(e.target.value),
                                            doc.startPage,
                                            doc.totalPages,
                                        ),
                                    })
                                }
                                className="field px-3 py-2.5 font-mono text-sm"
                            />
                        </div>
                    </div>

                    <div className="flex flex-col gap-2">
                        <label className="eyebrow">language hint</label>
                        <div className="flex flex-wrap gap-2">
                            {LANGUAGES.map((l) => (
                                <button
                                    type="button"
                                    key={l.code || "auto"}
                                    onClick={() =>
                                        update({ languageHint: l.code })
                                    }
                                    className={`chip ${
                                        doc.languageHint === l.code
                                            ? "is-active"
                                            : ""
                                    }`}
                                >
                                    {l.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    <button
                        type="button"
                        onClick={() =>
                            update({ aiGeneration: !doc.aiGeneration })
                        }
                        className="flex items-center gap-3 group"
                    >
                        <span
                            className={`cbox ${
                                doc.aiGeneration ? "" : "off"
                            }`}
                        >
                            {doc.aiGeneration && (
                                <svg
                                    width="12"
                                    height="12"
                                    viewBox="0 0 12 12"
                                    fill="none"
                                >
                                    <path
                                        d="M2.5 6.5L5 9L9.5 3.5"
                                        stroke="currentColor"
                                        strokeWidth="1.6"
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                    />
                                </svg>
                            )}
                        </span>
                        <span className="text-left flex flex-col">
                            <span className="text-sm text-ink">
                                Allow AI generation
                            </span>
                            <span className="eyebrow normal-case tracking-normal">
                                fills gaps when OCR is incomplete · ~1.6× output
                                tokens
                            </span>
                        </span>
                    </button>

                    <div className="rule" />

                    <div className="flex items-end justify-between gap-4">
                        <div className="flex flex-col">
                            <span className="eyebrow">estimated · usd</span>
                            <span className="font-mono text-2xl shimmer">
                                {formatCost(estimatedCost)}
                            </span>
                            <span className="eyebrow normal-case tracking-normal">
                                {pagesToProcess} pages
                                {selectedModel &&
                                    ` · ${selectedModel.model_name}`}
                            </span>
                        </div>

                        <button
                            type="button"
                            onClick={onExtract}
                            disabled={busy || !selectedModel}
                            className="btn-primary px-6 py-3 text-xs"
                        >
                            {busy ? "EXTRACTING…" : "EXTRACT"}
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};
