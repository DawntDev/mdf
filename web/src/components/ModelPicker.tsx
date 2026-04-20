import type { ApiModel } from "../types";

interface ModelPickerProps {
    models: ApiModel[];
    selected: ApiModel | null;
    onSelect: (model: ApiModel) => void;
    cheapestId?: string | null;
}

const formatPrice = (usdPerMtok: number) => {
    if (usdPerMtok >= 1) return `$${usdPerMtok.toFixed(2)}`;
    return `$${usdPerMtok.toFixed(3)}`;
};

const formatContext = (tokens: number) => {
    if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`;
    if (tokens >= 1_000) return `${Math.round(tokens / 1_000)}k`;
    return `${tokens}`;
};

export const ModelPicker = ({
    models,
    selected,
    onSelect,
    cheapestId,
}: ModelPickerProps) => {
    return (
        <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
                <span className="eyebrow">model</span>
                <span className="eyebrow">{models.length} available</span>
            </div>

            <div className="flex flex-col gap-2 max-h-72 overflow-y-auto minimal-scroll pr-1">
                {models.length === 0 && (
                    <div className="eyebrow text-center py-6">— loading models —</div>
                )}

                {models.map((m) => {
                    const isActive = selected?.id === m.id;
                    const isCheapest = cheapestId === m.id;

                    return (
                        <button
                            type="button"
                            key={m.id}
                            onClick={() => onSelect(m)}
                            className={`glass-soft text-left p-3 transition-all ${
                                isActive
                                    ? "border-line-strong bg-white/[0.04]"
                                    : "hover:bg-white/[0.03]"
                            }`}
                            style={
                                isActive
                                    ? { borderColor: "var(--line-strong)" }
                                    : undefined
                            }
                        >
                            <div className="flex items-center justify-between gap-3">
                                <div className="flex items-center gap-2 min-w-0">
                                    <span
                                        className={`dot ${
                                            isActive ? "dot-ok" : ""
                                        }`}
                                        style={
                                            isActive
                                                ? undefined
                                                : {
                                                      background: "transparent",
                                                      border: "1px solid var(--line-strong)",
                                                  }
                                        }
                                    />
                                    <div className="flex flex-col min-w-0">
                                        <span className="font-mono text-xs text-ink truncate">
                                            {m.model_name}
                                        </span>
                                        <span className="eyebrow truncate">
                                            {m.provider}
                                        </span>
                                    </div>
                                </div>

                                <div className="flex items-center gap-2 shrink-0">
                                    {isCheapest && (
                                        <span className="chip is-active">cheap</span>
                                    )}
                                    {m.supports_structured_output && (
                                        <span className="chip">json</span>
                                    )}
                                </div>
                            </div>

                            <div className="mt-2 pl-5 flex items-center gap-4 font-mono text-[11px] text-ink-dim">
                                <span>
                                    in {formatPrice(m.input_price_usd_per_mtok)}
                                    <span className="text-ink-faint">/M</span>
                                </span>
                                <span>
                                    out {formatPrice(m.output_price_usd_per_mtok)}
                                    <span className="text-ink-faint">/M</span>
                                </span>
                                <span className="ml-auto text-ink-faint">
                                    ctx {formatContext(m.context_window)}
                                </span>
                            </div>
                        </button>
                    );
                })}
            </div>
        </div>
    );
};
