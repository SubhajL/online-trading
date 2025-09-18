'use client'

import React, { createContext, useContext, useState, useCallback, useMemo } from 'react'
import type { Order, Position, Balance, OrderId } from '@/types'
import { mergeOrderUpdate } from '@/utils/mergeUpdates'

type TradingState = {
  orders: Order[]
  positions: Position[]
  balances: Balance[]
  isConnected: boolean
  isLoading: boolean
  error: Error | null
}

type TradingActions = {
  setOrders: (orders: Order[]) => void
  updateOrder: (update: Partial<Order> & { orderId: OrderId }) => void
  addOrder: (order: Order) => void
  setPositions: (positions: Position[]) => void
  setBalances: (balances: Balance[]) => void
  setConnectionState: (connected: boolean) => void
  setLoading: (loading: boolean) => void
  setError: (error: Error) => void
  clearError: () => void
  reset: () => void
}

type TradingContextValue = {
  state: TradingState
  actions: TradingActions
}

const TradingContext = createContext<TradingContextValue | undefined>(undefined)

const initialState: TradingState = {
  orders: [],
  positions: [],
  balances: [],
  isConnected: false,
  isLoading: false,
  error: null,
}

export function TradingProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<TradingState>(initialState)

  const setOrders = useCallback((orders: Order[]) => {
    setState(prev => ({ ...prev, orders }))
  }, [])

  const updateOrder = useCallback((update: Partial<Order> & { orderId: OrderId }) => {
    setState(prev => ({
      ...prev,
      orders: mergeOrderUpdate(prev.orders, update),
    }))
  }, [])

  const addOrder = useCallback((order: Order) => {
    setState(prev => ({
      ...prev,
      orders: [...prev.orders, order],
    }))
  }, [])

  const setPositions = useCallback((positions: Position[]) => {
    setState(prev => ({ ...prev, positions }))
  }, [])

  const setBalances = useCallback((balances: Balance[]) => {
    setState(prev => ({ ...prev, balances }))
  }, [])

  const setConnectionState = useCallback((connected: boolean) => {
    setState(prev => ({ ...prev, isConnected: connected }))
  }, [])

  const setLoading = useCallback((loading: boolean) => {
    setState(prev => ({ ...prev, isLoading: loading }))
  }, [])

  const setError = useCallback((error: Error) => {
    setState(prev => ({ ...prev, error }))
  }, [])

  const clearError = useCallback(() => {
    setState(prev => ({ ...prev, error: null }))
  }, [])

  const reset = useCallback(() => {
    setState(initialState)
  }, [])

  const actions = useMemo<TradingActions>(
    () => ({
      setOrders,
      updateOrder,
      addOrder,
      setPositions,
      setBalances,
      setConnectionState,
      setLoading,
      setError,
      clearError,
      reset,
    }),
    [
      setOrders,
      updateOrder,
      addOrder,
      setPositions,
      setBalances,
      setConnectionState,
      setLoading,
      setError,
      clearError,
      reset,
    ]
  )

  const value = useMemo<TradingContextValue>(
    () => ({
      state,
      actions,
    }),
    [state, actions]
  )

  return <TradingContext.Provider value={value}>{children}</TradingContext.Provider>
}

export function useTradingContext() {
  const context = useContext(TradingContext)

  if (context === undefined) {
    throw new Error('useTradingContext must be used within a TradingProvider')
  }

  return context
}