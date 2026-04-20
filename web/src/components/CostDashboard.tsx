import type { ApiModel, ApiQuote, DocumentState } from "../types";
import { formatCost } from "../utils";

interface CostDashboardProps {
    doc: DocumentState | null;
    selectedModel: ApiModel | null;
    quotes: ApiQuote[];
    cheapestId: string | null;
    pricingLastUpdated: string | null;
}

const formatTokens = (n: number) => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
    return `${n}`;
};

export const CostDashboard = ({
    doc,
    selectedModel,
    quotes,
    cheapestId,
    pricingLastUpdated,
}: CostDashboardProps) => {
    const selectedQuote =
        selectedModel ? quotes.find((q) => q.model_id === selectedModel.id) : null;
    const cheapestQuote =
        cheapestId ? quotes.find((q) => q.model_id === cheapestId) : null;

    return (
        <div className="glass p-6 flex flex-col gap-5">
            <div className="flex items-center justify-between">
                <div className="flex flex-col">
                    <span className="eyebrow">cost · snapshot</span>
                    <h3 className="text-lg font-medium text-ink">
                        {selectedModel ? selectedModel.model_name : "no model"}
                    </h3>
                </div>
                <span className="chip">
                    {doc ? `${doc.endPage - doc.startPage + 1}p` : "0p"}
                </span>
            </div>

            <div className="grid grid-cols-2 gap-3">
                <div className="glass-soft p-3 flex flex-col">
                    <span className="eyebrow">in tokens</span>
                    <span className="font-mono text-lg text-ink">
                        {selectedQuote
                            ? formatTokens(selectedQuote.estimated_input_tokens)
                            : "—"}
                    </span>
                </div>
                <div className="glass-soft p-3 flex flex-col">
                    <span className="eyebrow">out tokens</span>
                    <span className="font-mono text-lg text-ink">
                        {selectedQuote
                            ? formatTokens(selectedQuote.estimated_output_tokens)
                            : "—"}
                    </span>
                </div>
            </div>

            <div className="glass-soft p-4 flex flex-col gap-1">
                <span className="eyebrow">total · selected</span>
                <span className="font-mono text-3xl shimmer">
                    {formatCost(selectedQuote?.estimated_cost_usd)}
                </span>
            </div>

            {cheapestQuote && selectedModel && cheapestId !== selectedModel.id && (
                <div className="flex items-center justify-between gap-3 p-3 rounded-xl border border-line">
                    <div className="flex flex-col min-w-0">
                        <span className="eyebrow">cheapest option</span>
                        <span className="font-mono text-xs text-ink truncate">
                            {cheapestQuote.model_id}
                        </span>
                    </div>
                    <span className="font-mono text-sm text-accent">
                        {formatCost(cheapestQuote.estimated_cost_usd)}
                    </span>
                </div>
            )}

            {pricingLastUpdated && (
                <div className="eyebrow normal-case tracking-wider">
                    pricing · {pricingLastUpdated}
                </div>
            )}
        </div>
    );
};
