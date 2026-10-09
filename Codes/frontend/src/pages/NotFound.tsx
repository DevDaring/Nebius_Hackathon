import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ClownfishSvg } from "@/components/Clownfish";

export default function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto flex max-w-md flex-col items-center px-4 py-24 text-center">
      <ClownfishSvg className="h-12 w-24 opacity-80" />
      <p className="num mt-4 text-6xl font-extrabold text-marigold-ink">404</p>
      <h1 className="mt-4 text-xl font-bold">{t("errors.notFound")}</h1>
      <p className="mt-1 text-sm text-ink-3" lang="en">
        {t("app.name")}
      </p>
      <Link to="/" className="btn-primary mt-6">
        {t("errors.goHome")}
      </Link>
    </div>
  );
}
