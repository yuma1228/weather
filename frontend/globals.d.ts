// CSS の side-effect import (import "./globals.css") を tsc に認識させる。
// Next.js のビルドは CSS を直接扱うが、素の tsc --noEmit では型宣言が必要。
declare module "*.css";
