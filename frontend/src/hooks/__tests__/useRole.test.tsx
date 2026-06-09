import React from 'react';
import { render, screen } from '@testing-library/react';
import { RoleGate } from '../useRole';
import * as AuthProvider from '@/providers/AuthProvider';

// Mock the AuthProvider
jest.mock('@/providers/AuthProvider', () => ({
  useAuth: jest.fn(),
}));

describe('Property 30: Client-side RBAC Enforcement', () => {
  const setupMockUser = (role: string) => {
    (AuthProvider.useAuth as jest.Mock).mockReturnValue({
      user: { role },
    });
  };

  const TestComponent = ({ roles }: { roles: string[] }) => (
    <RoleGate roles={roles} fallback={<div data-testid="fallback">Access Denied</div>}>
      <div data-testid="protected-content">Secret Content</div>
    </RoleGate>
  );

  const roles = ['admin', 'operator', 'compliance', 'read_only'];

  it('Property: For any role/action combination, permitted actions are visible and non-permitted actions fallback', () => {
    // We test all combinations of user roles against all possible required roles
    roles.forEach(userRole => {
      roles.forEach(requiredRole => {
        setupMockUser(userRole);
        const { unmount } = render(<TestComponent roles={[requiredRole]} />);

        if (userRole === requiredRole) {
          // Permitted
          expect(screen.getByTestId('protected-content')).toBeInTheDocument();
          expect(screen.queryByTestId('fallback')).not.toBeInTheDocument();
        } else {
          // Non-permitted
          expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
          expect(screen.getByTestId('fallback')).toBeInTheDocument();
        }

        unmount();
      });
    });
  });

  it('Property: Multiple permitted roles allows any matching user role', () => {
    setupMockUser('operator');
    
    // operator is in the list
    const { unmount: unmount1 } = render(<TestComponent roles={['admin', 'operator']} />);
    expect(screen.getByTestId('protected-content')).toBeInTheDocument();
    unmount1();

    // operator is not in the list
    setupMockUser('visitor');
    const { unmount: unmount2 } = render(<TestComponent roles={['admin', 'operator']} />);
    expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
    expect(screen.getByTestId('fallback')).toBeInTheDocument();
    unmount2();
  });
});
