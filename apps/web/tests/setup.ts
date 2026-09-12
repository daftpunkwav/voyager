import '@testing-library/jest-dom/vitest';

// Vitest needs the development build; otherwise React Testing Library's act() is unavailable.
process.env.NODE_ENV = 'development';
