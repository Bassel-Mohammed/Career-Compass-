import { screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { render } from '../test/utils';
import { RolePicker } from './RolePicker';
import { ROLES } from '../auth/roles';

describe('RolePicker Component', () => {
  it('renders all provided roles', () => {
    const roles = ['JOB_SEEKER', 'EMPLOYER', 'ADMIN'] as const;
    const handleChange = vi.fn();

    render(
      <RolePicker
        legend="Select your role"
        roles={roles}
        value="JOB_SEEKER"
        onChange={handleChange}
      />
    );

    // Should render the legend
    expect(screen.getByText('Select your role')).toBeInTheDocument();

    // Should render options for each role
    roles.forEach((role) => {
      expect(screen.getByLabelText(ROLES[role].label)).toBeInTheDocument();
    });

    // Should render the hint for the selected role
    expect(screen.getByText(ROLES['JOB_SEEKER'].hint)).toBeInTheDocument();
  });

  it('calls onChange when a different role is selected', () => {
    const roles = ['JOB_SEEKER', 'EMPLOYER'] as const;
    const handleChange = vi.fn();

    render(
      <RolePicker
        legend="Select your role"
        roles={roles}
        value="JOB_SEEKER"
        onChange={handleChange}
      />
    );

    const employerRadio = screen.getByLabelText(ROLES['EMPLOYER'].label);
    fireEvent.click(employerRadio);

    expect(handleChange).toHaveBeenCalledWith('EMPLOYER');
    expect(handleChange).toHaveBeenCalledTimes(1);
  });
});
