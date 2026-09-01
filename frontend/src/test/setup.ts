import '@testing-library/jest-dom';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Runs after each test case to clear the DOM
afterEach(() => {
  cleanup();
});
