// Match the API/export Decimal(str(quantity))*Decimal(str(price)), ROUND_HALF_UP.
// Decimal coefficients are integers; binary floating-point never chooses a tie.
function decimalParts(value) {
  const text = String(value).toLowerCase();
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/.test(text)) throw new RangeError("Invalid money input");
  const [mantissa, exponent = "0"] = text.split("e");
  const negative = mantissa.startsWith("-");
  const unsigned = mantissa.replace(/^[+-]/, "");
  const [whole, fraction = ""] = unsigned.split(".");
  let coefficient = BigInt((whole || "0") + fraction) * (negative ? -1n : 1n);
  let scale = fraction.length - Number(exponent);
  if (Math.abs(scale) > 1000) throw new RangeError("Money scale is too large");
  if (scale < 0) { coefficient *= 10n ** BigInt(-scale); scale = 0; }
  return { coefficient, scale };
}

export function lineMoneyCents(quantity, price) {
  const q = decimalParts(quantity), p = decimalParts(price);
  let coefficient = q.coefficient * p.coefficient;
  const negative = coefficient < 0n;
  if (negative) coefficient = -coefficient;
  const scale = q.scale + p.scale;
  let cents;
  if (scale <= 2) cents = coefficient * 10n ** BigInt(2 - scale);
  else {
    const divisor = 10n ** BigInt(scale - 2);
    cents = coefficient / divisor + (coefficient % divisor * 2n >= divisor ? 1n : 0n);
  }
  return negative ? -cents : cents;
}

export const roundedLineAmount = (quantity, price) => Number(lineMoneyCents(quantity, price)) / 100;
export const sumRoundedAmounts = amounts => Number(amounts.reduce((sum, amount) => sum + lineMoneyCents(amount, 1), 0n)) / 100;
