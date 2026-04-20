import type { ApiHealthResponse } from "../types";

interface ProviderHealthProps {
    health: ApiHealthResponse | null;
}

export const ProviderHealth = ({ health }: ProviderHealthProps) => {
    const providers = health?.providers ?? [];
    const ocrAvailable = health?.ocr_available ?? false;

    return (
        <div className="glass-soft p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between">
                <span className="eyebrow">providers · status</span>
                {health && (
                    <span className="font-mono text-[10.5px] text-ink-faint uppercase tracking-wider">
                        {health.app_env}
                    </span>
                )}
            </div>

            <div className="flex flex-wrap gap-2">
                {providers.length === 0 && (
                    <span className="eyebrow">— no providers reported —</span>
                )}

                {providers.map((p) => (
                    <div
                        key={p.provider}
                        className="chip flex items-center gap-2"
                        style={{ cursor: "default" }}
                    >
                        <span className={`dot ${p.enabled ? "dot-ok" : "dot-err"}`} />
                        <span>{p.provider}</span>
                    </div>
                ))}

                <div className="chip flex items-center gap-2" style={{ cursor: "default" }}>
                    <span className={`dot ${ocrAvailable ? "dot-ok" : "dot-warn"}`} />
                    <span>ocr</span>
                </div>
            </div>

            {health?.ocr_error && (
                <p className="eyebrow text-danger normal-case tracking-normal">
                    ocr: {health.ocr_error}
                </p>
            )}
        </div>
    );
};
