import { useEffect, useMemo } from "react";

interface FilePreviewProps {
    file: File;
}

const IMAGE_EXTS = new Set(["png", "jpg", "jpeg", "webp", "gif"]);

export const FilePreview = ({ file }: FilePreviewProps) => {
    const url = useMemo(() => URL.createObjectURL(file), [file]);

    useEffect(() => {
        return () => URL.revokeObjectURL(url);
    }, [url]);

    const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
    const isPdf = file.type === "application/pdf" || ext === "pdf";
    const isImage = file.type.startsWith("image/") || IMAGE_EXTS.has(ext);

    return (
        <div className="flex flex-col gap-2">
            <span className="eyebrow">preview</span>
            {isPdf ? (
                <div className="rounded-xl border border-line overflow-hidden bg-black/20">
                    <iframe
                        key={url}
                        src={url}
                        title={file.name}
                        className="w-full h-[520px] block"
                    />
                </div>
            ) : isImage ? (
                <div className="rounded-xl border border-line overflow-hidden bg-black/20 flex items-center justify-center">
                    <img
                        src={url}
                        alt={file.name}
                        className="max-w-full max-h-[520px] object-contain"
                    />
                </div>
            ) : (
                <div className="rounded-xl border border-line p-8 flex flex-col items-center justify-center gap-2 text-center glass-soft">
                    <div className="font-mono text-2xl text-ink-dim">—</div>
                    <div className="eyebrow">
                        no inline preview for .{ext || "file"}
                    </div>
                </div>
            )}
        </div>
    );
};
