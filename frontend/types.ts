
export enum SidebarState {
    Collapsed = 'collapsed',
    Expanded = 'expanded'
}

export interface PriceHistoryData {
    productName: string;
    lowestPrice: number | null;
    highestPrice: number | null;
    averagePrice: number | null;
    currentPrice: number | null;
    trend: 'declining' | 'rising' | 'stable' | 'unknown';
    recommendation: 'STRONG_BUY' | 'BUY' | 'WAIT' | 'NEUTRAL';
    recommendationReason: string;
    chartImageUrl: string | null;
    sourceUrl: string | null;
}

export interface Message {
    id: string;
    role: 'user' | 'model';
    content: string;
    timestamp: Date;
    // Omnibox: Rich content fields
    imagePreview?: string;         // Base64 data URL of user-uploaded image
    productThumbnail?: string;     // Product image URL from backend
    attachedUrl?: string;          // URL pasted by user
    // Price History: Structured data for rich rendering
    priceHistory?: PriceHistoryData;
}

export interface ProgressStep {
    node: string;     // LangGraph node name
    label: string;    // User-friendly label (e.g., "Searching across sources...")
    status: 'pending' | 'active' | 'done';
}

export type AttachmentType = 'url' | 'image' | null;

export interface ChatSession {
    id: string;
    title: string;
    updatedAt: Date;
}
