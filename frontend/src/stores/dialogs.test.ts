import { authTarget, openDialog, useDialogs } from './dialogs'

it('öffnet und schließt', () => {
  openDialog('providers')
  expect(useDialogs.getState().current).toBe('providers')
  useDialogs.getState().close()
  expect(useDialogs.getState().current).toBeNull()
})

it('🔑 führt zum Web-Login nur mit Claude Code und Pseudo-Terminal', () => {
  expect(authTarget({ cli: true, can_web_login: true })).toBe('login')
  expect(authTarget({ cli: true, can_web_login: false })).toBe('claude')
  expect(authTarget({ cli: false, can_web_login: true })).toBe('claude')
  expect(authTarget(undefined)).toBe('claude')
})
