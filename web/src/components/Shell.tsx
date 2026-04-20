import type { ReactNode } from "react";

interface ShellProps {
    children: ReactNode;
}

export const Shell = ({ children }: ShellProps) => {
    return (
        <div className="min-h-screen flex flex-col">
            <header className="px-6 md:px-10 pt-8 pb-6">
                <div className="max-w-6xl mx-auto flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-xl bg-[#eceef1] text-[#0a0b0f] flex items-center justify-center font-mono font-bold text-sm">
                            m
                        </div>
                        <div className="flex flex-col leading-tight">
                            <span className="eyebrow">mdf / v0.1</span>
                            <span className="font-mono text-sm text-ink">
                                document extractor
                            </span>
                        </div>
                    </div>
                </div>
            </header>

            <main className="flex-1 px-6 md:px-10 pb-16">
                <div className="max-w-6xl mx-auto">{children}</div>
            </main>

            <footer className="px-6 md:px-10 py-6 border-t border-line">
                <div className="max-w-6xl mx-auto flex items-center justify-between eyebrow">
                    <span>made with caffeine & friction</span>
                    <span>· mdf ·</span>
                </div>
            </footer>
        </div>
    );
};
