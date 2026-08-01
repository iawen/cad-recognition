import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';

// 仅在显式开启 VITE_USE_MOCKS=true 时启动 MSW；默认联调真实后端。
async function bootstrap() {
  if (import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS === 'true') {
    const { worker } = await import('./mock/browser');
    await worker.start({
      onUnhandledRequest: 'bypass',
      quiet: true,
    });
  }

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>
  );
}

bootstrap();
