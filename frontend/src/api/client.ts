import axios from 'axios';
import { useAuthStore } from '../store/authStore';

const apiClient = axios.create({
  baseURL: '/api/v1',
});

apiClient.interceptors.request.use((config) => {
  const apiKey = useAuthStore.getState().apiKey;
  if (apiKey) {
    config.headers.Authorization = `Bearer ${apiKey}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().clearAuth();
      window.location.href = '/settings';
    }
    return Promise.reject(error);
  }
);

export default apiClient;
