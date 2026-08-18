
import { Message } from '../types';

export const sendMessageToGemini = async (history: Message[], text: string, apiKey: string): Promise<string> => {
    // Logic to call backend API would go here.
    // For now, returning a mock response to satisfy the interface.
    await new Promise(resolve => setTimeout(resolve, 1000));
    return "This is a simulated response from the Aether Advisor. Backend integration pending.";
};
