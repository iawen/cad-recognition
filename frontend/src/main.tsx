import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';

// 启动 MSW mock 服务（同事接入真实后端时，注释掉下面这两行即可）
async function bootstrap() {
  // 开发环境下启动 MSW
  if (import.meta.env.DEV) {
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
