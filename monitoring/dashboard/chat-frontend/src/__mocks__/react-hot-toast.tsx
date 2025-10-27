import React from 'react';

// Mock toast function
const toast: any = jest.fn();
toast.success = jest.fn();
toast.error = jest.fn();
toast.loading = jest.fn();
toast.custom = jest.fn();
toast.dismiss = jest.fn();
toast.remove = jest.fn();
toast.promise = jest.fn();

// Mock Toaster component
export const Toaster: React.FC = () => <div data-testid="mock-toaster" />;

export default toast;
