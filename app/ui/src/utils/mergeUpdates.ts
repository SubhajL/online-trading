import type { Order, OrderId } from '@/types'

export function mergeOrderUpdate(
  orders: Order[],
  update: Partial<Order> & { orderId: OrderId }
): Order[] {
  const orderIndex = orders.findIndex(order => order.orderId === update.orderId)

  // If order not found, return original array
  if (orderIndex === -1) {
    return orders
  }

  // Create a new array with the updated order
  const updatedOrders = [...orders]
  updatedOrders[orderIndex] = {
    ...orders[orderIndex]!,
    ...update,
  }

  return updatedOrders
}