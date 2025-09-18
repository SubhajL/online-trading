import type { OrderFormValues } from './OrderForm'

export function validateOrderForm(values: OrderFormValues): Record<string, string> {
  const errors: Record<string, string> = {}

  // Validate symbol
  if (!values.symbol) {
    errors.symbol = 'Symbol is required'
  } else if (!/^[A-Z0-9]+$/.test(values.symbol)) {
    errors.symbol = 'Invalid symbol format'
  }

  // Validate quantity
  if (!values.quantity || values.quantity === 0) {
    errors.quantity = 'Quantity is required'
  } else if (values.quantity < 0) {
    errors.quantity = 'Quantity must be positive'
  }

  // Validate price for limit orders
  if (values.type === 'LIMIT' && (!values.price || values.price === 0)) {
    errors.price = 'Price is required for limit orders'
  } else if (values.type === 'LIMIT' && values.price && values.price < 0) {
    errors.price = 'Price must be positive'
  }

  return errors
}
