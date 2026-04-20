import { useCallback, useEffect, useMemo, useState } from "react";
import { Shell } from "./components/Shell";
import { UploadForm } from "./components/UploadForm";
import { ModelPicker } from "./components/ModelPicker";
import { CostDashboard } from "./components/CostDashboard";
import { ProviderHealth } from "./components/ProviderHealth";
import { ExtractionResults } from "./components/ExtractionResults";
import type {
    ApiHealthResponse,
    ApiModel,
    ApiQuote,
    ApiQuoteResponse,
    DocumentState,
    ExtractionResult,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const api = (path: string) => `${API_BASE}${path}`;

const App = () => {
    const [doc, setDoc] = useState<DocumentState | null>(null);
    const [models, setModels] = useState<ApiModel[]>([]);
    const [selectedModel, setSelectedModel] = useState<ApiModel | null>(null);
    const [quotes, setQuotes] = useState<ApiQuote[]>([]);
    const [cheapestId, setCheapestId] = useState<string | null>(null);
    const [pricingLastUpdated, setPricingLastUpdated] = useState<string | null>(
        null,
    );
    const [health, setHealth] = useState<ApiHealthResponse | null>(null);
    const [busy, setBusy] = useState(false);
    const [textSample, setTextSample] = useState<string>("");
    const [extraction, setExtraction] = useState<ExtractionResult | null>(null);

    useEffect(() => {
        const controller = new AbortController();

        const loadModels = async () => {
            try {
                const res = await fetch(api("/api/v1/models"), {
                    signal: controller.signal,
                });
                if (!res.ok) return;
                const data = (await res.json()) as { models: ApiModel[] };
                setModels(data.models);
                if (data.models.length > 0) setSelectedModel(data.models[0]);
            } catch (err) {
                if ((err as Error).name !== "AbortError") {
                    console.error("Error fetching models:", err);
                }
            }
        };

        const loadHealth = async () => {
            try {
                const res = await fetch(api("/api/v1/health"), {
                    signal: controller.signal,
                });
                if (!res.ok) return;
                const data = (await res.json()) as ApiHealthResponse;
                setHealth(data);
            } catch (err) {
                if ((err as Error).name !== "AbortError") {
                    console.error("Error fetching health:", err);
                }
            }
        };

        loadModels();
        loadHealth();

        return () => controller.abort();
    }, []);

    useEffect(() => {
        if (!doc?.file) return;
        let cancelled = false;
        const SAMPLE_BYTES = 16 * 1024;
        doc.file
            .slice(0, SAMPLE_BYTES)
            .text()
            .then((s) => {
                if (!cancelled) setTextSample(s.length > 0 ? s : doc.name);
            })
            .catch(() => {
                if (!cancelled) setTextSample(doc.name);
            });
        return () => {
            cancelled = true;
        };
    }, [doc?.file, doc?.name]);

    const handleSetDoc = useCallback((next: DocumentState | null) => {
        setDoc(next);
        if (!next) {
            setTextSample("");
            setQuotes([]);
            setCheapestId(null);
        }
    }, []);

    const pagesToProcess = doc ? doc.endPage - doc.startPage + 1 : 0;
    const outputMultiplier = doc?.aiGeneration ? 1.6 : 1.0;
    const modelIds = useMemo(() => models.map((m) => m.id), [models]);

    useEffect(() => {
        if (!textSample || modelIds.length === 0 || pagesToProcess <= 0) {
            return;
        }

        const controller = new AbortController();
        const timer = window.setTimeout(async () => {
            try {
                const res = await fetch(api("/api/v1/quote"), {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        text_sample: textSample,
                        models: modelIds,
                        expected_pages: pagesToProcess,
                        output_token_multiplier: outputMultiplier,
                    }),
                    signal: controller.signal,
                });
                if (!res.ok) return;
                const data = (await res.json()) as ApiQuoteResponse;
                setQuotes(data.quotes);
                setCheapestId(data.cheapest_model_id);
                setPricingLastUpdated(data.pricing_last_updated);
            } catch (err) {
                if ((err as Error).name !== "AbortError") {
                    console.error("Error fetching quote:", err);
                }
            }
        }, 300);

        return () => {
            controller.abort();
            window.clearTimeout(timer);
        };
    }, [textSample, modelIds, pagesToProcess, outputMultiplier]);


    const handleExtract = useCallback(async () => {
        if (!doc || !selectedModel) return;
        setBusy(true);
        setExtraction(null);

        const formData = new FormData();
        formData.append("file", doc.file);
        formData.append("model", selectedModel.id);
        if (doc.languageHint) formData.append("language_hint", doc.languageHint);
        const pagesToProcess = doc.endPage - doc.startPage + 1;
        formData.append("max_pages", pagesToProcess.toString());
        formData.append("allow_ai_generation", doc.aiGeneration.toString());

        try {
            const res = await fetch(api("/api/v1/extract"), {
                method: "POST",
                body: formData,
            });
            if (!res.ok) throw new Error("Extract failed");
            const data = (await res.json()) as ExtractionResult;
            setExtraction(data);
        } catch (err) {
            console.error("Error extracting document:", err);
            alert("Hubo un error al procesar el documento.");
        } finally {
            setBusy(false);
        }
    }, [doc, selectedModel]);

    const handleClearExtraction = useCallback(() => setExtraction(null), []);

    const estimatedCost =
        selectedModel && quotes.length > 0
            ? quotes.find((q) => q.model_id === selectedModel.id)
                  ?.estimated_cost_usd ?? null
            : null;

    return (
        <Shell>
            <div className="flex flex-col gap-6">
                <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
                    <div className="lg:col-span-3">
                        <UploadForm
                            doc={doc}
                            onDoc={handleSetDoc}
                            selectedModel={selectedModel}
                            estimatedCost={estimatedCost}
                            onExtract={handleExtract}
                            busy={busy}
                        />
                    </div>

                    <div className="lg:col-span-2 flex flex-col gap-6">
                        <CostDashboard
                            doc={doc}
                            selectedModel={selectedModel}
                            quotes={quotes}
                            cheapestId={cheapestId}
                            pricingLastUpdated={pricingLastUpdated}
                        />
                        <div className="glass p-6">
                            <ModelPicker
                                models={models}
                                selected={selectedModel}
                                onSelect={setSelectedModel}
                                cheapestId={cheapestId}
                            />
                        </div>
                    </div>
                </div>

                {extraction && (
                    <ExtractionResults
                        result={extraction}
                        onClear={handleClearExtraction}
                    />
                )}

                <ProviderHealth health={health} />
            </div>
        </Shell>
    );
};

export default App;
