import { defineConfig } from '@apps-in-toss/web-framework/config';

export default defineConfig({
  appName: 'recall',
  brand: {
    primaryColor: '#3182F6',
  },
  // 바코드 화면의 사진 판독용. 앱 진입 시가 아니라 버튼을 눌렀을 때만 요청한다.
  permissions: [
    { name: 'camera', access: 'access' },
    { name: 'photos', access: 'read' },
  ],
  webBundleDir: 'dist',
});
