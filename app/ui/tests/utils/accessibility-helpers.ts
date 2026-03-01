import { Page, expect } from '@playwright/test'
import { injectAxe, checkA11y, getViolations } from '@axe-core/playwright'

export class AccessibilityHelpers {
  constructor(private page: Page) {}

  async setupAxe() {
    await injectAxe(this.page)
  }

  async checkPageAccessibility(options?: {
    include?: string[]
    exclude?: string[]
    tags?: string[]
    rules?: Record<string, { enabled: boolean }>
  }) {
    await this.setupAxe()
    
    const axeOptions = {
      tags: options?.tags || ['wcag2a', 'wcag2aa', 'wcag21aa'],
      include: options?.include,
      exclude: options?.exclude,
      rules: options?.rules,
    }

    await checkA11y(this.page, undefined, axeOptions)
  }

  async getAccessibilityViolations(selector?: string) {
    await this.setupAxe()
    return await getViolations(this.page, selector)
  }

  async checkKeyboardNavigation(startSelector: string, expectedOrder: string[]) {
    await this.page.locator(startSelector).focus()
    
    for (let i = 0; i < expectedOrder.length; i++) {
      const currentFocus = await this.page.evaluate(() => document.activeElement?.getAttribute('data-testid'))
      expect(currentFocus).toBe(expectedOrder[i])
      
      if (i < expectedOrder.length - 1) {
        await this.page.keyboard.press('Tab')
      }
    }
  }

  async checkAriaLabels(selectors: Record<string, string>) {
    for (const [selector, expectedLabel] of Object.entries(selectors)) {
      const element = this.page.locator(selector)
      await expect(element).toHaveAttribute('aria-label', expectedLabel)
    }
  }

  async checkHeadingStructure() {
    const headings = await this.page.locator('h1, h2, h3, h4, h5, h6').all()
    const headingLevels: number[] = []
    
    for (const heading of headings) {
      const tagName = await heading.evaluate(el => el.tagName.toLowerCase())
      const level = parseInt(tagName.charAt(1))
      headingLevels.push(level)
    }
    
    // Check that heading levels are logical (no skipping levels)
    for (let i = 1; i < headingLevels.length; i++) {
      const currentLevel = headingLevels[i]
      const previousLevel = headingLevels[i - 1]
      
      if (currentLevel > previousLevel + 1) {
        throw new Error(`Heading level skip detected: h${previousLevel} followed by h${currentLevel}`)
      }
    }
    
    return headingLevels
  }

  async checkColorContrast(selector: string, minRatio: number = 4.5) {
    const element = this.page.locator(selector)
    
    const contrastRatio = await element.evaluate((el, minRatio) => {
      const styles = window.getComputedStyle(el)
      const backgroundColor = styles.backgroundColor
      const color = styles.color
      
      // This is a simplified contrast check
      // In a real implementation, you'd use a proper color contrast library
      const bgLuminance = this.getLuminance(backgroundColor)
      const textLuminance = this.getLuminance(color)
      
      const ratio = (Math.max(bgLuminance, textLuminance) + 0.05) / 
                   (Math.min(bgLuminance, textLuminance) + 0.05)
      
      return ratio
    }, minRatio)
    
    expect(contrastRatio).toBeGreaterThanOrEqual(minRatio)
    return contrastRatio
  }

  async checkFocusVisibility(selector: string) {
    const element = this.page.locator(selector)
    await element.focus()
    
    // Check if focus indicator is visible
    const focusStyles = await element.evaluate(el => {
      const styles = window.getComputedStyle(el, ':focus')
      return {
        outline: styles.outline,
        outlineWidth: styles.outlineWidth,
        outlineStyle: styles.outlineStyle,
        outlineColor: styles.outlineColor,
        boxShadow: styles.boxShadow,
      }
    })
    
    const hasFocusIndicator = 
      focusStyles.outline !== 'none' ||
      focusStyles.outlineWidth !== '0px' ||
      focusStyles.boxShadow !== 'none'
    
    expect(hasFocusIndicator).toBe(true)
    return focusStyles
  }

  async checkTouchTargetSize(selector: string, minSize: number = 44) {
    const element = this.page.locator(selector)
    const boundingBox = await element.boundingBox()
    
    if (!boundingBox) {
      throw new Error(`Element ${selector} not found or not visible`)
    }
    
    expect(boundingBox.width).toBeGreaterThanOrEqual(minSize)
    expect(boundingBox.height).toBeGreaterThanOrEqual(minSize)
    
    return boundingBox
  }

  async checkScreenReaderText(selector: string, expectedText: string) {
    const element = this.page.locator(selector)
    
    // Check aria-label
    const ariaLabel = await element.getAttribute('aria-label')
    if (ariaLabel) {
      expect(ariaLabel).toContain(expectedText)
      return
    }
    
    // Check aria-labelledby
    const ariaLabelledBy = await element.getAttribute('aria-labelledby')
    if (ariaLabelledBy) {
      const labelElement = this.page.locator(`#${ariaLabelledBy}`)
      await expect(labelElement).toContainText(expectedText)
      return
    }
    
    // Check aria-describedby
    const ariaDescribedBy = await element.getAttribute('aria-describedby')
    if (ariaDescribedBy) {
      const descElement = this.page.locator(`#${ariaDescribedBy}`)
      await expect(descElement).toContainText(expectedText)
      return
    }
    
    // Check text content
    await expect(element).toContainText(expectedText)
  }

  async checkFormLabels() {
    const inputs = await this.page.locator('input, select, textarea').all()
    
    for (const input of inputs) {
      const id = await input.getAttribute('id')
      const ariaLabel = await input.getAttribute('aria-label')
      const ariaLabelledBy = await input.getAttribute('aria-labelledby')
      
      if (!ariaLabel && !ariaLabelledBy && id) {
        // Check for associated label
        const label = this.page.locator(`label[for="${id}"]`)
        await expect(label).toBeVisible()
      }
    }
  }

  async checkImageAltText() {
    const images = await this.page.locator('img').all()
    
    for (const img of images) {
      const alt = await img.getAttribute('alt')
      const role = await img.getAttribute('role')
      
      // Images should have alt text unless they're decorative (role="presentation")
      if (role !== 'presentation' && role !== 'none') {
        expect(alt).toBeTruthy()
      }
    }
  }

  async checkLandmarkRoles() {
    const requiredLandmarks = ['main', 'navigation', 'banner', 'contentinfo']
    
    for (const landmark of requiredLandmarks) {
      const element = this.page.locator(`[role="${landmark}"], ${landmark}`)
      await expect(element).toBeVisible()
    }
  }

  async simulateScreenReader() {
    // Simulate screen reader navigation
    const focusableElements = await this.page.locator(
      'a, button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
    ).all()
    
    const screenReaderOutput: string[] = []
    
    for (const element of focusableElements) {
      await element.focus()
      
      const tagName = await element.evaluate(el => el.tagName.toLowerCase())
      const text = await element.textContent()
      const ariaLabel = await element.getAttribute('aria-label')
      const role = await element.getAttribute('role')
      
      const announcement = ariaLabel || text || `${tagName} ${role || 'element'}`
      screenReaderOutput.push(announcement.trim())
    }
    
    return screenReaderOutput
  }

  async checkResponsiveDesign(breakpoints: Record<string, { width: number; height: number }>) {
    const results: Record<string, boolean> = {}
    
    for (const [name, viewport] of Object.entries(breakpoints)) {
      await this.page.setViewportSize(viewport)
      
      // Check if layout adapts properly
      const isResponsive = await this.page.evaluate(() => {
        // Check for horizontal scrollbars
        const hasHorizontalScroll = document.body.scrollWidth > window.innerWidth
        
        // Check if text is readable (not too small)
        const textElements = document.querySelectorAll('p, span, div')
        let minFontSize = Infinity
        
        textElements.forEach(el => {
          const fontSize = parseFloat(window.getComputedStyle(el).fontSize)
          if (fontSize > 0 && fontSize < minFontSize) {
            minFontSize = fontSize
          }
        })
        
        return !hasHorizontalScroll && minFontSize >= 14
      })
      
      results[name] = isResponsive
    }
    
    return results
  }
}
