import { useEffect, useMemo, useState } from "react";
import type { ExtractionResult, MdfEntry, MdfValue } from "../types";
import { formatCost } from "../utils";

interface ExtractionResultsProps {
    result: ExtractionResult;
    onClear: () => void;
}

type MdfValueKey = Exclude<keyof MdfEntry, "source_page" | "id" | "lexeme">;

const ENTRY_FIELDS: Array<{ key: MdfValueKey; label: string }> = [
    { key: "part_of_speech", label: "pos" },
    { key: "sense_number", label: "sense" },
    { key: "subentry", label: "subentry" },
    { key: "phonetic_transcription", label: "phonetic" },
    { key: "morphological_representation", label: "morph" },
    { key: "definition_en", label: "def · en" },
    { key: "definition_es", label: "def · es" },
    { key: "gloss_en", label: "gloss · en" },
    { key: "gloss_es", label: "gloss · es" },
    { key: "example_vernacular", label: "example" },
    { key: "example_translation_en", label: "ex · en" },
    { key: "example_translation_es", label: "ex · es" },
    { key: "example_source", label: "ex src" },
    { key: "cross_reference", label: "cross-ref" },
    { key: "lexical_function", label: "lex fn" },
    { key: "related_lexeme", label: "related" },
    { key: "etymology", label: "etymology" },
    { key: "scientific_name", label: "sci. name" },
    { key: "location", label: "location" },
    { key: "general_notes", label: "notes" },
    { key: "audio_file", label: "audio" },
    { key: "video_file", label: "video" },
    { key: "image_file", label: "image" },
];

const AiTag = () => (
    <span
        className="text-[9px] font-mono uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border border-accent/50 text-accent shrink-0 leading-none"
        title="AI generated — no literal support in source"
    >
        ai
    </span>
);

const hasValue = (v: MdfValue | undefined | null): v is MdfValue =>
    !!v && v.value !== null && v.value !== "";

const EntryCard = ({ entry }: { entry: MdfEntry }) => {
    const populated = ENTRY_FIELDS.filter(({ key }) => hasValue(entry[key]));
    const lexeme = entry.lexeme ?? { value: null, ai_generated: false };
    const id = entry.id ?? { value: null, ai_generated: false };
    const pos = entry.part_of_speech;

    return (
        <div className="glass-soft p-5 flex flex-col gap-3 hover:border-line-strong transition-colors">
            <div className="flex items-start justify-between gap-3 pb-3 border-b border-line">
                <div className="flex items-baseline gap-2 min-w-0 flex-wrap">
                    {id.value && (
                        <span className="font-mono text-[11px] text-ink-faint">
                            {id.value}
                        </span>
                    )}
                    <span className="text-lg font-medium text-ink truncate">
                        {lexeme.value ?? "—"}
                    </span>
                    {lexeme.ai_generated && <AiTag />}
                    {hasValue(pos) && (
                        <span className="eyebrow">· {pos.value}</span>
                    )}
                </div>
                {entry.source_page != null && (
                    <span className="chip shrink-0">p.{entry.source_page}</span>
                )}
            </div>

            {populated.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-5 gap-y-2">
                    {populated.map(({ key, label }) => {
                        const v = entry[key];
                        if (!v) return null;
                        return (
                            <div
                                key={key}
                                className="flex items-baseline gap-2"
                            >
                                <span className="eyebrow shrink-0 w-20">
                                    {label}
                                </span>
                                <span className="text-sm text-ink min-w-0 flex-1 wrap-break-word">
                                    {v.value}
                                </span>
                                {v.ai_generated && <AiTag />}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};

export const ExtractionResults = ({
    result,
    onClear,
}: ExtractionResultsProps) => {
    const dictionary = result.dictionary;
    const metadata = dictionary.metadata;
    const entries = dictionary.entries ?? [];
    const pages_with_errors = dictionary.pages_with_errors ?? [];
    const warnings = result.warnings ?? [];
    const total_entries_extracted =
        dictionary.total_entries_extracted ?? entries.length;

    const [query, setQuery] = useState("");

    useEffect(() => {
        const prev = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        const onKey = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClear();
        };
        window.addEventListener("keydown", onKey);
        return () => {
            document.body.style.overflow = prev;
            window.removeEventListener("keydown", onKey);
        };
    }, [onClear]);

    const aiCount = useMemo(
        () =>
            entries.reduce((acc, e) => {
                let n = 0;
                for (const { key } of ENTRY_FIELDS) {
                    if (e[key]?.ai_generated) n += 1;
                }
                if (e.lexeme?.ai_generated) n += 1;
                if (e.id?.ai_generated) n += 1;
                return acc + n;
            }, 0),
        [entries],
    );

    const handleDownload = () => {
        const json = JSON.stringify(result, null, 2);
        const blob = new Blob([json], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        const baseName =
            metadata.source_file?.replace(/\.[^/.]+$/, "") ?? "extraction";
        a.href = url;
        a.download = `${baseName}.mdf.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    const filteredEntries = useMemo(() => {
        const q = query.trim().toLowerCase();
        if (!q) return entries;
        return entries.filter((e) => {
            const lexeme = e.lexeme?.value?.toLowerCase() ?? "";
            const id = e.id?.value?.toLowerCase() ?? "";
            if (lexeme.includes(q) || id.includes(q)) return true;
            for (const { key } of ENTRY_FIELDS) {
                const v = e[key]?.value?.toLowerCase();
                if (v && v.includes(q)) return true;
            }
            return false;
        });
    }, [entries, query]);

    return (
        <div
            className="fixed inset-0 z-50 flex flex-col bg-[#0a0b0f]/95 backdrop-blur-xl"
            role="dialog"
            aria-modal="true"
        >
            <header className="shrink-0 border-b border-line px-6 md:px-10 py-5">
                <div className="max-w-350 mx-auto flex items-center justify-between gap-4 flex-wrap">
                    <div className="flex flex-col leading-tight">
                        <span className="eyebrow">
                            step · 02 · extraction complete
                        </span>
                        <h2 className="text-xl md:text-2xl font-medium text-ink">
                            <span className="shimmer">
                                {total_entries_extracted}
                            </span>{" "}
                            entries extracted
                        </h2>
                    </div>
                    <div className="flex items-center gap-2">
                        <input
                            type="search"
                            placeholder="search lexeme, id, definition…"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            className="field px-3 py-2 text-sm w-64 font-mono"
                        />
                        <button
                            type="button"
                            onClick={handleDownload}
                            className="chip border-accent/50 text-accent"
                            title="Download extraction as JSON"
                        >
                            download · json
                        </button>
                        <button
                            type="button"
                            onClick={onClear}
                            className="chip is-danger"
                            title="Close (Esc)"
                        >
                            close · esc
                        </button>
                    </div>
                </div>
            </header>

            <main className="flex-1 overflow-y-auto minimal-scroll">
                <div className="max-w-350 mx-auto px-6 md:px-10 py-6 flex flex-col gap-6">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div className="glass-soft p-4 flex flex-col gap-1">
                            <span className="eyebrow">source</span>
                            <span className="font-mono text-xs text-ink truncate">
                                {metadata.source_file}
                            </span>
                        </div>
                        <div className="glass-soft p-4 flex flex-col gap-1">
                            <span className="eyebrow">pages</span>
                            <span className="font-mono text-sm text-ink">
                                {metadata.total_pages}
                            </span>
                        </div>
                        <div className="glass-soft p-4 flex flex-col gap-1">
                            <span className="eyebrow">model</span>
                            <span className="font-mono text-xs text-ink truncate">
                                {metadata.model_used}
                            </span>
                        </div>
                        <div className="glass-soft p-4 flex flex-col gap-1">
                            <span className="eyebrow">cost · usd</span>
                            <span className="font-mono text-sm text-ink">
                                {formatCost(metadata.estimated_cost_usd)}
                            </span>
                        </div>
                    </div>

                    <div className="flex flex-wrap gap-2 items-center">
                        <span className="chip">
                            pdf · {metadata.pdf_type || "unknown"}
                        </span>
                        {metadata.language && (
                            <span className="chip">
                                lang · {metadata.language}
                            </span>
                        )}
                        <span className="chip">
                            order · {metadata.extraction_order}
                        </span>
                        {aiCount > 0 && (
                            <span className="chip border-accent/50 text-accent">
                                {aiCount} ai-generated fields
                            </span>
                        )}
                        {query && (
                            <span className="chip">
                                {filteredEntries.length} / {entries.length}{" "}
                                match
                            </span>
                        )}
                    </div>

                    {warnings.length > 0 && (
                        <div className="glass-soft p-4 flex flex-col gap-1 border-l-2 border-warn">
                            <span className="eyebrow text-warn">warnings</span>
                            <ul className="text-xs text-ink-dim flex flex-col gap-0.5">
                                {warnings.map((w, i) => (
                                    <li key={i}>· {w}</li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {pages_with_errors.length > 0 && (
                        <div className="glass-soft p-4 flex flex-col gap-1 border-l-2 border-danger">
                            <span className="eyebrow text-danger">
                                page errors
                            </span>
                            <ul className="text-xs text-ink-dim flex flex-col gap-0.5">
                                {pages_with_errors.map((e, i) => (
                                    <li key={i}>
                                        p.{e.page_number} · {e.error_type}:{" "}
                                        {e.message}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {entries.length > 0 ? (
                        filteredEntries.length > 0 ? (
                            <div className="flex flex-col gap-3 pb-8">
                                {filteredEntries.map((entry, i) => (
                                    <EntryCard
                                        key={`${entry.id?.value ?? "entry"}-${i}`}
                                        entry={entry}
                                    />
                                ))}
                            </div>
                        ) : (
                            <div className="glass-soft p-8 text-center eyebrow">
                                no entries match "{query}"
                            </div>
                        )
                    ) : (
                        <div className="glass-soft p-8 text-center eyebrow">
                            no entries extracted
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
};
