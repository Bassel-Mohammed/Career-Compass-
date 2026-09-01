import { describe, it, expect } from 'vitest';
import { prerequisiteFor, messageFor, isAiFailure } from './errors';
import { ApiError, TimeoutError, NetworkError } from './client';

describe('API Errors Utility', () => {
  describe('messageFor', () => {
    it('returns the message from an ApiError', () => {
      const error = new ApiError(400, 'BAD_REQUEST', 'Invalid input provided', []);
      expect(messageFor(error)).toBe('Invalid input provided');
    });

    it('adds extra context for AI failures (502-504)', () => {
      const error = new ApiError(503, 'AI_TIMEOUT', 'Service unavailable', []);
      expect(messageFor(error)).toBe('Service unavailable The analysis service may still be starting up.');
    });

    it('returns the message from NetworkError or TimeoutError', () => {
      expect(messageFor(new NetworkError())).toContain('Could not reach');
      expect(messageFor(new TimeoutError(5000))).toContain('took longer than');
    });

    it('returns generic message for unknown objects', () => {
      expect(messageFor({})).toBe('Something went wrong. Please try again.');
    });
  });

  describe('isAiFailure', () => {
    it('identifies 502, 503, 504 as AI failures', () => {
      expect(isAiFailure(new ApiError(502, 'ERR', 'msg', []))).toBe(true);
      expect(isAiFailure(new ApiError(503, 'ERR', 'msg', []))).toBe(true);
      expect(isAiFailure(new ApiError(504, 'ERR', 'msg', []))).toBe(true);
    });

    it('returns false for other status codes', () => {
      expect(isAiFailure(new ApiError(500, 'ERR', 'msg', []))).toBe(false);
      expect(isAiFailure(new ApiError(400, 'ERR', 'msg', []))).toBe(false);
    });
  });

  describe('prerequisiteFor', () => {
    it('returns proper routing for career path missing', () => {
      const error = new ApiError(400, 'PREREQUISITE_NOT_MET', 'Missing career path', []);
      const req = prerequisiteFor(error, 'JOB_SEEKER');
      expect(req).toEqual({
        to: '/setup',
        message: 'Choose the career path you want to be measured against first.',
      });
    });

    it('returns different routing for study field missing based on role', () => {
      const error = new ApiError(400, 'PREREQUISITE_NOT_MET', 'Missing study field', []);

      const contentManagerReq = prerequisiteFor(error, 'CONTENT_MANAGER');
      expect(contentManagerReq?.to).toBe('/content/profile');

      const jobSeekerReq = prerequisiteFor(error, 'JOB_SEEKER');
      expect(jobSeekerReq?.to).toBe('/setup');
    });
  });
});
