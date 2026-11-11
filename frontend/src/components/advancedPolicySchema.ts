export type Schema = Record<string, unknown>;
export function asSchema(value: unknown): Schema {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Schema)
    : {};
}
export function variants(schema: Schema): Schema[] {
  const union = schema.anyOf ?? schema.oneOf;
  return Array.isArray(union) ? union.map(asSchema) : [schema];
}
export function allowsNull(schema: Schema): boolean {
  return variants(schema).some(
    (item) =>
      item.type === "null" ||
      (Array.isArray(item.type) && item.type.includes("null")),
  );
}
export function inputSchema(schema: Schema): Schema {
  const choices = variants(schema).filter((item) => item.type !== "null");
  if (choices.length !== 1) return schema;
  const choice = { ...schema, ...choices[0] };
  if (Array.isArray(choice.type)) {
    const types = choice.type.filter((type) => type !== "null");
    if (types.length === 1) choice.type = types[0];
  }
  return choice;
}

export function editableValue(value: unknown, schema: Schema): unknown {
  const shape = inputSchema(schema);
  if (Array.isArray(value))
    return value.map((item) => editableValue(item, asSchema(shape.items)));
  if (value !== null && typeof value === "object") {
    const properties = asSchema(shape.properties);
    return Object.fromEntries(
      Object.entries(value).flatMap(([name, item]) => {
        if (shape.properties && !(name in properties)) return [];
        const nested = properties[name] ?? shape.additionalProperties;
        return [[name, editableValue(item, asSchema(nested))]];
      }),
    );
  }
  return value;
}
export function validateValue(
  value: unknown,
  schema: Schema,
  path: string,
): void {
  const fail = (message: string): never => {
    throw new Error(`${path}: ${message}`);
  };
  const union = schema.anyOf ?? schema.oneOf;
  if (Array.isArray(union)) {
    if (
      !union.some((item) => {
        try {
          validateValue(value, asSchema(item), path);
          return true;
        } catch {
          return false;
        }
      })
    )
      fail("value does not match an allowed type or constraint.");
  }
  const types = Array.isArray(schema.type)
    ? schema.type
    : schema.type
      ? [schema.type]
      : [];
  if (
    types.length &&
    !types.some((type) => {
      if (type === "null") return value === null;
      if (type === "object")
        return (
          value !== null && typeof value === "object" && !Array.isArray(value)
        );
      if (type === "array") return Array.isArray(value);
      if (type === "integer")
        return typeof value === "number" && Number.isInteger(value);
      return typeof value === type;
    })
  )
    fail("invalid value type.");
  if (
    Array.isArray(schema.enum) &&
    !schema.enum.some((item) => JSON.stringify(item) === JSON.stringify(value))
  )
    fail("choose an allowed value.");
  if (typeof value === "number") {
    if (!Number.isFinite(value)) fail("enter a finite number.");
    if (typeof schema.minimum === "number" && value < schema.minimum)
      fail(`minimum is ${schema.minimum}.`);
    if (typeof schema.maximum === "number" && value > schema.maximum)
      fail(`maximum is ${schema.maximum}.`);
    if (
      typeof schema.exclusiveMinimum === "number" &&
      value <= schema.exclusiveMinimum
    )
      fail(`must exceed ${schema.exclusiveMinimum}.`);
    if (
      typeof schema.exclusiveMaximum === "number" &&
      value >= schema.exclusiveMaximum
    )
      fail(`must be below ${schema.exclusiveMaximum}.`);
  }
  if (typeof value === "string") {
    if (typeof schema.minLength === "number" && value.length < schema.minLength)
      fail(`minimum length is ${schema.minLength}.`);
    if (typeof schema.maxLength === "number" && value.length > schema.maxLength)
      fail(`maximum length is ${schema.maxLength}.`);
  }
  if (Array.isArray(value)) {
    if (typeof schema.minItems === "number" && value.length < schema.minItems)
      fail(`at least ${schema.minItems} items required.`);
    if (typeof schema.maxItems === "number" && value.length > schema.maxItems)
      fail(`at most ${schema.maxItems} items allowed.`);
    if (schema.items)
      value.forEach((item, i) =>
        validateValue(item, asSchema(schema.items), `${path}[${i}]`),
      );
  } else if (value !== null && typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (Array.isArray(schema.required))
      schema.required.forEach((name) => {
        if (typeof name === "string" && !(name in record))
          fail(`${name} is required.`);
      });
    const properties = asSchema(schema.properties);
    Object.entries(record).forEach(([name, item]) => {
      if (name in properties)
        validateValue(item, asSchema(properties[name]), `${path}.${name}`);
      else if (schema.additionalProperties === false)
        fail(`unknown property ${name}.`);
      else if (typeof schema.additionalProperties === "object")
        validateValue(
          item,
          asSchema(schema.additionalProperties),
          `${path}.${name}`,
        );
    });
  }
}
