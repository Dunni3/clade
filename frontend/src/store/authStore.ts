import { create } from 'zustand';

interface AuthState {
  apiKey: string | null;
  brotherName: string | null;
  setAuth: (apiKey: string, brotherName: string) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  apiKey: localStorage.getItem('mailbox_api_key'),
  brotherName: localStorage.getItem('mailbox_brother_name'),
  setAuth: (apiKey: string, brotherName: string) => {
    localStorage.setItem('mailbox_api_key', apiKey);
    localStorage.setItem('mailbox_brother_name', brotherName);
    set({ apiKey, brotherName });
  },
  clearAuth: () => {
    localStorage.removeItem('mailbox_api_key');
    localStorage.removeItem('mailbox_brother_name');
    set({ apiKey: null, brotherName: null });
  },
}));
