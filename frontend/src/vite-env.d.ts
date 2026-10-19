/// <reference types="vite/client" />

declare module '*.css' {
  const content: Record<string, string>;
  export default content;
}

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_ADS_MODE?: string
  readonly VITE_AD_GROUP_HOME?: string
}
