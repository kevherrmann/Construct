import { render } from '@testing-library/react'
import type { Nachricht, Person } from '@/api/team'
import { NachrichtKarte } from './NachrichtKarte'

const leute: Record<string, Person> = {
  chef: { name: 'Chefin', title: '', color: '1,2,3', avatar: '' },
}

// Auftrag 350744b0: Die Blase zeigte, was die Chefin am Ende ihres Zugs sagte; im
// Verlauf stand nur ihre Lieferung, das Gesagte war ausgeblendet.
it('zeigt, was jemand im Zug gesagt hat, im Verlauf wie jede Nachricht', () => {
  const e: Nachricht = {
    id: 'm1',
    ts: 1,
    von: 'chef',
    an: '',
    art: 'gesagt',
    text: 'Der Großtest ist durch.',
  }
  const { container } = render(<NachrichtKarte e={e} leute={leute} />)
  expect(container.textContent).toContain('Der Großtest ist durch.')
  expect(container.textContent).toContain('CHEFIN')
})
