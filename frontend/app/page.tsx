import { redirect } from "next/navigation";

// ルートは熱中症リスクページへ
export default function Home() {
  redirect("/heatstroke");
}
