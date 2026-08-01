import { http, HttpResponse, delay } from 'msw';
import { mockSymbolsWithInstances, mockTables, mockTexts } from './data/recognition.mock';

/** 所有 MSW handler 聚合 */
export const handlers = [
  // 登录
  http.post('/api/auth/login', async ({ request }) => {
    await delay(500);
    const body = (await request.json()) as { username: string; password: string };
    if (body.username === 'admin' && body.password === '123456') {
      return HttpResponse.json({
        code: 0,
        message: 'ok',
        data: { token: 'mock-token-2024', user: { username: 'admin' } },
      });
    }
    return HttpResponse.json(
      { code: 401, message: '用户名或密码错误', data: null },
      { status: 401 }
    );
  }),

  // 上传文件
  http.post('/api/upload', async () => {
    await delay(1000);
    const taskId = 'task-' + Date.now();
    return HttpResponse.json({
      code: 0,
      message: 'ok',
      data: { taskId },
    });
  }),

  // 查询任务状态
  http.get('/api/recognition/:taskId', async () => {
    await delay(300);
    return HttpResponse.json({
      code: 0,
      message: 'ok',
      data: {
        taskId: 'task-demo-001',
        fileName: '电气主接线图.dwg',
        fileSize: 2048576,
        status: 'completed',
        progress: 100,
        createdAt: '2026-07-28T10:30:00Z',
        completedAt: '2026-07-28T10:31:30Z',
        imageUrl: '/cad-drawing.png',
        imageWidth: 1200,
        imageHeight: 900,
        sheets: [
          { index: 0, name: '分布式光伏发电系统 10kV 高压接入一次接线配置图' },
          { index: 1, name: '分布式光伏发电系统 0.4kV 低压侧接线图' },
          { index: 2, name: '分布式光伏发电系统接入用户侧一次接线图' },
        ],
      },
    });
  }),

  // 获取符号列表
  http.get('/api/recognition/:taskId/symbols', async () => {
    await delay(400);
    return HttpResponse.json({
      code: 0,
      message: 'ok',
      data: mockSymbolsWithInstances,
    });
  }),

  // 获取表格列表
  http.get('/api/recognition/:taskId/tables', async () => {
    await delay(300);
    return HttpResponse.json({
      code: 0,
      message: 'ok',
      data: mockTables,
    });
  }),

  // 获取文字列表
  http.get('/api/recognition/:taskId/texts', async () => {
    await delay(300);
    return HttpResponse.json({
      code: 0,
      message: 'ok',
      data: mockTexts,
    });
  }),
];
