import { create } from 'zustand';

interface AuthState {
  apiKey: string | null;
  brotherName: string | null;
  setAuth: (apiKey: string, brotherName: string) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  apiKey: localStorage.getItem('hearth_api_key') || localStorage.getItem('mailbox_api_key'),
  brotherName: localStorage.getItem('hearth_brother_name') || localStorage.getItem('mailbox_brother_name'),
  setAuth: (apiKey: string, brotherName: string) => {
    localStorage.setItem('hearth_api_key', apiKey);
    localStorage.setItem('hearth_brother_name', brotherName);
    // Clean up legacy keys
    localStorage.removeItem('mailbox_api_key');
    localStorage.removeItem('mailbox_brother_name');
    set({ apiKey, brotherName });
  },
  clearAuth: () => {
    localStorage.removeItem('hearth_api_key');
    localStorage.removeItem('hearth_brother_name');
    localStorage.removeItem('mailbox_api_key');
    localStorage.removeItem('mailbox_brother_name');
    set({ apiKey: null, brotherName: null });
  },
}));
