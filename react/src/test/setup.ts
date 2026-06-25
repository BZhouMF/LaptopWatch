import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement scrollTo
window.scrollTo = () => {};
