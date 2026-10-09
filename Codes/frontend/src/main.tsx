import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LazyMotion, MotionConfig } from "framer-motion";
import { i18nReady } from "./i18n";
import "./index.css";
import { App } from "./App";
import { ApiError } from "./api/http";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: (count, err) =>
        !(
          err instanceof ApiError &&
          [400, 401, 403, 404, 422].includes(err.status)
        ) && count < 1,
    },
  },
});

// Components use the light `m` component (imported as `motion`); animation features load lazily.
const motionFeatures = () =>
  import("./lib/motionFeatures").then((m) => m.default);

const root = ReactDOM.createRoot(document.getElementById("root")!);
// Render once the stored language's strings are loaded (English is bundled; others are a small chunk).
void i18nReady.finally(() =>
  root.render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <LazyMotion features={motionFeatures} strict>
          <MotionConfig reducedMotion="user">
            <BrowserRouter
              future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
            >
              <App />
            </BrowserRouter>
          </MotionConfig>
        </LazyMotion>
      </QueryClientProvider>
    </React.StrictMode>,
  ),
);
