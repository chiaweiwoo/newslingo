import React from 'react';
import { createRoot } from 'react-dom/client';
import { ChakraProvider } from '@chakra-ui/react';
import theme from './theme';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { SpeechProvider } from './contexts/SpeechContext';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5 * 60 * 1000, retry: 1 },  // 5 min — refresh within session if stale
  },
});

const container = document.getElementById('root');
const root = createRoot(container!);
root.render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ChakraProvider theme={theme}>
        <SpeechProvider>
          <App />
        </SpeechProvider>
      </ChakraProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
