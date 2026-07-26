export {};

declare global {
  namespace NodeJS {
    interface ProcessEnv {
      TEST_FILE?: string;
    }
  }

  interface ImportMetaEnv {
    readonly TEST_FILE?: string;
  }

  var describe: (name: string, fn: () => void) => void;
  var it: (name: string, fn: () => void | Promise<void>) => void;
  var expect: (actual: unknown) => {
    toBeInTheDocument: () => void;
  };
}

declare module "*.png" {
  const src: string;
  export default src;
}
