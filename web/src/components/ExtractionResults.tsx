import { useEffect, useRef } from "react";
import type { ExtractionResult, MdfEntry, MdfValue } from "../types";
import { formatCost } from "../utils";

interface ExtractionResultsProps {
    result: {dictionary: ExtractionResult};
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
        <div className="glass-soft p-4 flex flex-col gap-3">
            <div className="flex items-start justify-between gap-3">
                <div className="flex items-baseline gap-2 min-w-0 flex-wrap">
                    {id.value && (
                        <span className="font-mono text-[11px] text-ink-faint">
                            {id.value}
                        </span>
                    )}
                    <span className="text-base font-medium text-ink truncate">
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
                <div className="flex flex-col gap-1.5">
                    {populated.map(({ key, label }) => {
                        const v = entry[key];
                        if (!v) return null;
                        return (
                            <div
                                key={key}
                                className="flex items-baseline gap-2"
                            >
                                <span className="eyebrow shrink-0 w-18">
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
    const rootRef = useRef<HTMLDivElement>(null);
    const metadata = result.dictionary.metadata ?? ({} as Partial<ExtractionResult["metadata"]>);
    const entries = result.dictionary.entries ?? [];
    const pages_with_errors = result.pages_with_errors ?? [];
    const warnings = result.warnings ?? [];
    const total_entries_extracted =
        result.total_entries_extracted ?? entries.length;

    useEffect(() => {
        rootRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, []);

    const aiCount = entries.reduce((acc, e) => {
        let n = 0;
        for (const { key } of ENTRY_FIELDS) {
            if (e[key]?.ai_generated) n += 1;
        }
        if (e.lexeme?.ai_generated) n += 1;
        if (e.id?.ai_generated) n += 1;
        return acc + n;
    }, 0);

    return (
        <div ref={rootRef} className="glass p-6 md:p-8 flex flex-col gap-6">
            <div className="flex items-center justify-between">
                <div className="flex flex-col">
                    <span className="eyebrow">step · 02 · extraction</span>
                    <h2 className="text-lg font-medium text-ink">
                        {total_entries_extracted} entries extracted
                    </h2>
                </div>
                <button
                    type="button"
                    onClick={onClear}
                    className="chip is-danger"
                >
                    dismiss
                </button>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="glass-soft p-3 flex flex-col">
                    <span className="eyebrow">source</span>
                    <span className="font-mono text-xs text-ink truncate">
                        {metadata.source_file}
                    </span>
                </div>
                <div className="glass-soft p-3 flex flex-col">
                    <span className="eyebrow">pages</span>
                    <span className="font-mono text-sm text-ink">
                        {metadata.total_pages}
                    </span>
                </div>
                <div className="glass-soft p-3 flex flex-col">
                    <span className="eyebrow">model</span>
                    <span className="font-mono text-xs text-ink truncate">
                        {metadata.model_used}
                    </span>
                </div>
                <div className="glass-soft p-3 flex flex-col">
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
                    <span className="chip">lang · {metadata.language}</span>
                )}
                <span className="chip">order · {metadata.extraction_order}</span>
                {aiCount > 0 && (
                    <span className="chip border-accent/50 text-accent">
                        {aiCount} ai-generated fields
                    </span>
                )}
            </div>

            {warnings.length > 0 && (
                <div className="glass-soft p-3 flex flex-col gap-1 border-l-2 border-warn">
                    <span className="eyebrow text-warn">warnings</span>
                    <ul className="text-xs text-ink-dim flex flex-col gap-0.5">
                        {warnings.map((w, i) => (
                            <li key={i}>· {w}</li>
                        ))}
                    </ul>
                </div>
            )}

            {pages_with_errors.length > 0 && (
                <div className="glass-soft p-3 flex flex-col gap-1 border-l-2 border-danger">
                    <span className="eyebrow text-danger">page errors</span>
                    <ul className="text-xs text-ink-dim flex flex-col gap-0.5">
                        {pages_with_errors.map((e, i) => (
                            <li key={i}>
                                p.{e.page_number} · {e.error_type}: {e.message}
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {entries.length > 0 ? (
                <div className="flex flex-col gap-3 max-h-[720px] overflow-y-auto minimal-scroll pr-2">
                    {entries.map((entry, i) => (
                        <EntryCard
                            key={`${entry.id?.value ?? "entry"}-${i}`}
                            entry={entry}
                        />
                    ))}
                </div>
            ) : (
                <div className="glass-soft p-6 text-center eyebrow">
                    no entries extracted
                </div>
            )}
        </div>
    );
};
