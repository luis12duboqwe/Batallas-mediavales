import { useEffect, useRef } from 'react';

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

const visibleFocusableElements = (dialog) => (
  Array.from(dialog?.querySelectorAll(FOCUSABLE_SELECTOR) || []).filter((element) => (
    element instanceof HTMLElement
    && !element.hasAttribute('hidden')
    && element.getAttribute('aria-hidden') !== 'true'
    && element.getClientRects().length > 0
  ))
);

const useModalAccessibility = (isOpen, onClose) => {
  const dialogRef = useRef(null);
  const onCloseRef = useRef(onClose);
  const previousFocusRef = useRef(null);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!isOpen) return undefined;

    previousFocusRef.current = document.activeElement;
    const dialog = dialogRef.current;
    const focusInsideDialog = (preferLast = false) => {
      const focusable = visibleFocusableElements(dialog);
      const target = preferLast ? focusable[focusable.length - 1] : focusable[0];
      (target || dialog)?.focus();
    };
    const focusFrame = window.requestAnimationFrame(() => focusInsideDialog(false));

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current?.();
        return;
      }
      if (event.key !== 'Tab' || !dialog) return;

      const focusable = visibleFocusableElements(dialog);
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }

      const active = document.activeElement;
      const activeIndex = focusable.indexOf(active);
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (!dialog.contains(active) || activeIndex === -1) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    const handleFocusIn = (event) => {
      if (!dialog || dialog.contains(event.target)) return;
      focusInsideDialog(false);
    };

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('focusin', handleFocusIn);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('focusin', handleFocusIn);
      const previous = previousFocusRef.current;
      window.requestAnimationFrame(() => {
        if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
      });
    };
  }, [isOpen]);

  return dialogRef;
};

export default useModalAccessibility;
