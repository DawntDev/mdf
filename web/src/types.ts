// --- API Types ---

export interface ApiModel {
    id: string;
    provider: string;
    model_name: string;
    input_price_usd_per_mtok: number;
    output_price_usd_per_mtok: number;
    context_window: number;
    supports_structured_output: boolean;
    pricing_last_updated: string;
}

export interface ApiProviderHealth {
    provider: string;
    enabled: boolean;
}

export interface ApiHealthResponse {
    status: string;
    app_env: string;
    providers: ApiProviderHealth[];
    ocr_available: boolean;
    ocr_error: string | null;
}

export interface ApiQuote {
    model_id: string;
    estimated_input_tokens: number;
    estimated_output_tokens: number;
    estimated_cost_usd: number;
    input_price_usd_per_mtok: number;
    output_price_usd_per_mtok: number;
}

export interface ApiQuoteResponse {
    quotes: ApiQuote[];
    cheapest_model_id: string;
    pricing_last_updated: string;
}

// --- Extraction Types ---

export interface MdfValue {
    value: string | null;
    ai_generated: boolean;
}

export interface MdfEntry {
    id: MdfValue;
    lexeme: MdfValue;
    part_of_speech: MdfValue;
    sense_number: MdfValue;
    subentry: MdfValue;
    phonetic_transcription: MdfValue;
    morphological_representation: MdfValue;
    definition_en: MdfValue;
    definition_es: MdfValue;
    gloss_en: MdfValue;
    gloss_es: MdfValue;
    example_vernacular: MdfValue;
    example_translation_en: MdfValue;
    example_translation_es: MdfValue;
    example_source: MdfValue;
    cross_reference: MdfValue;
    lexical_function: MdfValue;
    related_lexeme: MdfValue;
    audio_file: MdfValue;
    video_file: MdfValue;
    general_notes: MdfValue;
    etymology: MdfValue;
    scientific_name: MdfValue;
    location: MdfValue;
    image_file: MdfValue;
    source_page: number | null;
}

export interface MdfMetadata {
    source_file: string;
    total_pages: number;
    pdf_type: string;
    language: string | null;
    model_used: string;
    estimated_cost_usd: number;
    extraction_order: string;
    extracted_at: string;
}

export interface MdfPageError {
    page_number: number;
    error_type: string;
    message: string;
}

export interface MdfDictionary {
    metadata: MdfMetadata;
    entries: MdfEntry[];
    pages_with_errors: MdfPageError[];
    total_entries_extracted: number;
}

export interface ExtractionResult {
    dictionary: MdfDictionary;
    warnings: string[];
}

// --- App State Types ---

export interface DocumentState {
    file: File;
    name: string;
    size: number;
    totalPages: number;
    startPage: number; // Nuevo: Página de inicio
    endPage: number;   // Nuevo: Página de fin
    aiGeneration: boolean;
    languageHint: string;
}