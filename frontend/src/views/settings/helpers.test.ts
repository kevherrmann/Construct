import { previewStyle } from './helpers'

it('Vorschau dunkelt das Bild ab', () => {
  expect(previewStyle({ image: '/uploads/a.png' }, 60).backgroundImage).toBe(
    'linear-gradient(rgba(0,0,0,0.60),rgba(0,0,0,0.60)), url("/uploads/a.png")',
  )
  expect(previewStyle({ image: '' }, 60).backgroundImage).toBe('none')
})
