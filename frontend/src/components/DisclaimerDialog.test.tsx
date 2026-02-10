import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DisclaimerDialog } from './DisclaimerDialog';

describe('DisclaimerDialog', () => {
  it('renders nothing when open is false', () => {
    const { container } = render(
      <DisclaimerDialog open={false} onConfirm={vi.fn()} onCancel={vi.fn()} />
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders dialog content when open is true', () => {
    render(<DisclaimerDialog open={true} onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByText('disclaimer.title')).toBeInTheDocument();
    expect(screen.getByText('disclaimer.tool_desc')).toBeInTheDocument();
    expect(screen.getByText('disclaimer.copyright_title')).toBeInTheDocument();
    expect(screen.getByText('disclaimer.copyright_desc')).toBeInTheDocument();
  });

  it('calls onConfirm when confirm button is clicked', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<DisclaimerDialog open={true} onConfirm={onConfirm} onCancel={vi.fn()} />);
    await user.click(screen.getByText('disclaimer.confirm'));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it('calls onCancel when cancel button is clicked', async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(<DisclaimerDialog open={true} onConfirm={vi.fn()} onCancel={onCancel} />);
    await user.click(screen.getByText('disclaimer.cancel'));
    expect(onCancel).toHaveBeenCalledOnce();
  });
});
