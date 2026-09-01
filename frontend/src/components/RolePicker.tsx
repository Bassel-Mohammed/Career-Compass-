import { ROLES } from '../auth/roles';
import type { Role } from '../types';

interface Props {
  legend: string;
  roles: readonly Role[];
  value: Role;
  onChange: (role: Role) => void;
  disabled?: boolean;
}

/**
 * Which actor is signing in. This is not a preference — LoginRequest carries no role,
 * so the choice made here decides which of the five login endpoints is called.
 *
 * Built from real radio inputs rather than buttons so that arrow keys move between
 * options and the group reads correctly to assistive technology.
 */
export function RolePicker({ legend, roles, value, onChange, disabled }: Props) {
  return (
    <fieldset className="rolepicker" disabled={disabled}>
      <legend className="rolepicker__legend">{legend}</legend>
      <div className="rolepicker__options" data-count={roles.length}>
        {roles.map((role) => (
          <label
            key={role}
            className={`rolepicker__option${value === role ? ' rolepicker__option--on' : ''}`}
          >
            <input
              type="radio"
              name="role"
              value={role}
              checked={value === role}
              onChange={() => onChange(role)}
            />
            <span>{ROLES[role].label}</span>
          </label>
        ))}
      </div>
      <p className="rolepicker__hint">{ROLES[value].hint}</p>
    </fieldset>
  );
}
