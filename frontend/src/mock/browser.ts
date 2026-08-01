import { setupWorker } from 'msw/browser';
import { handlers } from './handlers';

/** MSW Worker 实例，在 main.tsx 中启动 */
export const worker = setupWorker(...handlers);
